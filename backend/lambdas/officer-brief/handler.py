"""Behind a Function URL. Writes a one-page officer brief per city, in English,
Hindi, from findings-<city>.json -- grounded so every number in the
output is checked against the input before it's ever shown.

POST body: {"city": "delhi", "language": "en" | "hi", "refresh": false}

The model only ever sees the findings JSON, never free text -- the system prompt
tells it to write for a ward drainage engineer before the monsoon: what floods,
why, what to do first, in plain language, with spot ids and units kept exact and
no number that isn't in the input. After generation every number in the output
(Latin or Devanagari digits) is checked against every number in the
input; one regeneration is allowed, then it fails rather than show an unverified
brief. Cached at analysis/briefs/<city>-<language>.json, keyed by a hash of the
findings content so a brief is only regenerated when the findings actually change.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

import boto3

OUTPUTS_BUCKET = os.environ["OUTPUTS_BUCKET"]
MODEL_ID = "us.amazon.nova-lite-v1:0"
# Nova Pro is larger and writes Hindi better than Nova Lite; English stays on Nova Lite.
MODELS = {"en": MODEL_ID, "hi": "us.amazon.nova-pro-v1:0"}
RATE_LIMIT_KEY = "analysis/briefs/_ratelimit.json"
RATE_LIMIT_PER_HOUR = 20  # fresh generations only; cached briefs are served free

s3 = boto3.client("s3")

SITE_BUCKET = os.environ.get("SITE_BUCKET")


def _publish_to_site(key: str, body: str) -> None:
    """The web app reads cached results through CloudFront from the site bucket, so copy each one there too."""
    if SITE_BUCKET:
        s3.put_object(Bucket=SITE_BUCKET, Key=key, Body=body, ContentType="application/json")

bedrock = boto3.client("bedrock-runtime")

LANGUAGE_NAMES = {"en": "English", "hi": "Hindi"}

SYSTEM_PROMPT = """You write a one-page brief for a ward drainage engineer, to read before the monsoon.
Use ONLY facts present in the JSON data you are given. Do not invent, estimate or round any number that
is not already in the data. Write in plain language: what floods, why, what to do first, in priority
order. Keep spot ids (like S1, S2) and units exactly as given. Write entirely in {language}, including
place names and spot ids in the original script too (for example: "S2, Kadubeesanahalli underpass") so
an engineer can cross-check against the English data.
Refer to each spot only by its id (S1, S2, ...) written exactly as given, in English letters. Never write a
place or road name: the reader already has a list of the spot ids with their names above your text. Use short plain sentences. Do not mention file names, code, software or data
sources. Do not say when the data was generated."""

# Latin and Devanagari (Hindi) digits, so a number written in either script is found.
_DIGIT_MAP = str.maketrans(
    "0123456789" "०१२३४५६७८९",
    "0123456789" "0123456789",
)
_NUMBER_RE = re.compile(r"[0-9०-९][0-9०-९,.]*[0-9०-९]|[0-9०-९]")


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        city = body["city"]
        language = body["language"]
        refresh = bool(body.get("refresh", False))
        if language not in LANGUAGE_NAMES:
            return _response(400, {"error": f"language must be one of {list(LANGUAGE_NAMES)}"})
    except (KeyError, json.JSONDecodeError, TypeError) as e:
        return _response(400, {"error": f"invalid request body: {e}"})
    if not (isinstance(city, str) and re.fullmatch(r"[a-z]{1,30}", city)):
        return _response(400, {"error": "city must be lowercase letters"})

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

    if not _check_rate_limit():
        return _response(429, {"error": f"rate limit: {RATE_LIMIT_PER_HOUR} new briefs per hour reached, try again later"})

    findings = json.loads(findings_raw)
    findings_numbers = _numbers_in(findings_raw.decode("utf-8"))
    must_appear = [str(sp["id"]) for sp in findings["spots"]]
    # The names are added by code, exactly as in the findings, so no language model can change them.
    legend = "\n".join(f"{sp['id']}: {sp['name']}" for sp in findings["spots"])
    model_input = json.dumps(_brief_input(findings), ensure_ascii=False)

    text = None
    problem = {}
    for attempt in range(3):
        candidate = _generate(model_input, language)
        bad = _numbers_in(candidate) - findings_numbers
        missing = [n for n in must_appear if n not in candidate]
        if not bad and not missing:
            text = f"{legend}\n\n{candidate}"
            break
        problem = {"unverifiedNumbers": sorted(bad), "spotIdsMissing": missing}
    if text is None:
        return _response(502, {"error": "brief failed verification: numbers not in the findings, or a spot id missing", **problem})

    result = {
        "city": city,
        "language": language,
        "text": text,
        "model": MODELS[language],
        "inputHash": findings_hash,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    s3.put_object(Bucket=OUTPUTS_BUCKET, Key=cache_key, Body=json.dumps(result), ContentType="application/json")
    _publish_to_site(cache_key, json.dumps(result))
    return _response(200, result)


def _generate(findings_json: str, language: str) -> str:
    response = bedrock.converse(
        modelId=MODELS[language],
        system=[{"text": SYSTEM_PROMPT.format(language=LANGUAGE_NAMES[language])}],
        messages=[{"role": "user", "content": [{"text": findings_json}]}],
        inferenceConfig={"maxTokens": 1500, "temperature": 0.2},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


def _brief_input(findings: dict) -> dict:
    """What the model is shown: the spots and the headline facts, without the methods text and
    internal references that have no place in a brief for an engineer."""
    keep = ("id", "name", "causeLabel", "why", "fix", "now", "priority", "confidence", "depthCm", "sizing", "directions")
    return {
        "city": findings.get("cityName"),
        "flaggedAtCm": findings.get("flagCm"),
        "spots": [{k: sp[k] for k in keep if k in sp} for sp in findings["spots"]],
    }


def _check_rate_limit() -> bool:
    """At most RATE_LIMIT_PER_HOUR fresh generations per hour overall, so a public URL cannot run up Bedrock cost."""
    now = time.time()
    record = _get_json(RATE_LIMIT_KEY) or {"calls": []}
    recent = [t for t in record["calls"] if now - t < 3600]
    if len(recent) >= RATE_LIMIT_PER_HOUR:
        return False
    recent.append(now)
    s3.put_object(Bucket=OUTPUTS_BUCKET, Key=RATE_LIMIT_KEY, Body=json.dumps({"calls": recent}), ContentType="application/json")
    return True


def _numbers_in(text: str) -> set[str]:
    """Every number in the text, digits normalised to Latin so Devanagari and
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
