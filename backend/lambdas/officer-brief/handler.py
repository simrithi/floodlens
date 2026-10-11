"""Behind a Function URL. Writes a one-page officer brief per city, in English,
Kannada or Hindi, from findings-<city>.json -- grounded so every number in the
output is checked against the input before it's ever shown.

POST body: {"city": "delhi", "language": "en" | "kn" | "hi", "refresh": false}

The model only ever sees the findings JSON, never free text -- the system prompt
tells it to write for a ward drainage engineer before the monsoon: what floods,
why, what to do first, in plain language, with spot ids and units kept exact and
no number that isn't in the input. After generation every number in the output
(Latin, Kannada or Devanagari digits) is checked against every number in the
input; one regeneration is allowed, then it fails rather than show an unverified
brief. Cached at analysis/briefs/<city>-<language>.json, keyed by a hash of the
findings content so a brief is only regenerated when the findings actually change.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone

import boto3

OUTPUTS_BUCKET = os.environ["OUTPUTS_BUCKET"]
MODEL_ID = "us.amazon.nova-lite-v1:0"

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

LANGUAGE_NAMES = {"en": "English", "kn": "Kannada", "hi": "Hindi"}

SYSTEM_PROMPT = """You write a one-page brief for a ward drainage engineer, to read before the monsoon.
Use ONLY facts present in the JSON data you are given. Do not invent, estimate or round any number that
is not already in the data. Write in plain language: what floods, why, what to do first, in priority
order. Keep spot ids (like S1, S2) and units exactly as given. Write entirely in {language}, including
place names and spot ids in the original script too (for example: "S2, Kadubeesanahalli underpass") so
an engineer can cross-check against the English data."""

# Latin, Devanagari (Hindi) and Kannada digits, so a number written in any of the three scripts is found.
_DIGIT_MAP = str.maketrans(
    "0123456789" "०१२३४५६७८९" "೦೧೨೩೪೫೬೭೮೯",
    "0123456789" "0123456789" "0123456789",
)
_NUMBER_RE = re.compile(r"[0-9०-९೦-೯][0-9०-९೦-೯,.]*[0-9०-९೦-೯]|[0-9०-९೦-೯]")


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        city = body["city"]
        language = body["language"]
        refresh = bool(body.get("refresh", False))
        if language not in LANGUAGE_NAMES:
            return _response(400, {"error": f"language must be one of {list(LANGUAGE_NAMES)}"})
    except (KeyError, json.JSONDecodeError) as e:
        return _response(400, {"error": f"invalid request body: {e}"})

    findings_key = f"analysis/findings-{city}.json"
    findings_raw = _get_raw(findings_key)
    if findings_raw is None:
        return _response(404, {"error": f"no findings-{city}.json in outputs bucket"})
    findings_hash = hashlib.sha256(findings_raw).hexdigest()[:16]

    cache_key = f"analysis/briefs/{city}-{language}.json"
    if not refresh:
        cached = _get_json(cache_key)
        if cached is not None and cached.get("inputHash") == findings_hash:
            return _response(200, cached)

    findings_numbers = _numbers_in(findings_raw.decode("utf-8"))

    text = None
    for attempt in range(2):
        candidate = _generate(findings_raw.decode("utf-8"), language)
        bad = _numbers_in(candidate) - findings_numbers
        if not bad:
            text = candidate
            break
    if text is None:
        return _response(502, {"error": "brief contained numbers not present in the findings data", "unverifiedNumbers": sorted(bad)})

    result = {
        "city": city,
        "language": language,
        "text": text,
        "model": MODEL_ID,
        "inputHash": findings_hash,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    s3.put_object(Bucket=OUTPUTS_BUCKET, Key=cache_key, Body=json.dumps(result), ContentType="application/json")
    return _response(200, result)


def _generate(findings_json: str, language: str) -> str:
    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT.format(language=LANGUAGE_NAMES[language])}],
        messages=[{"role": "user", "content": [{"text": findings_json}]}],
        inferenceConfig={"maxTokens": 1500, "temperature": 0.2},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


def _numbers_in(text: str) -> set[str]:
    """Every number in the text, digits normalised to Latin so Kannada/Devanagari and
    Latin spellings of the same number compare equal. Commas and a trailing/leading
    dot are stripped so '1,234' and '1234' and '1234.' all match."""
    out = set()
    for m in _NUMBER_RE.findall(text):
        norm = m.translate(_DIGIT_MAP).replace(",", "").strip(".")
        if norm:
            out.add(norm)
    return out


def _get_raw(key: str) -> bytes | None:
    try:
        return s3.get_object(Bucket=OUTPUTS_BUCKET, Key=key)["Body"].read()
    except s3.exceptions.NoSuchKey:
        return None


def _get_json(key: str) -> dict | None:
    raw = _get_raw(key)
    return None if raw is None else json.loads(raw)


def _response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }
