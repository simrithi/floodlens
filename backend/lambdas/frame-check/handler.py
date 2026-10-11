"""Behind a Function URL. Reads a flagged spot's dashcam frames and asks a vision model
what's actually visible at the drain inlet -- evidence for an engineer to verify on
site, never an input to the water model or any score.

POST body: {"city": "delhi", "spotId": "S2", "refresh": false}

Reads findings-<city>.json (the spot, its stretches) and analysis.json (each
stretch's frameIndexes) from the outputs bucket, picks the best frame plus up to
3 more, sends the *original* (not overlay) images to Amazon Nova Lite on Bedrock,
and asks for a fixed JSON schema. Caches the result at
analysis/checks/<city>/<spotId>.json; returns the cache unless refresh=true.

Rate-limited to 30 calls/hour overall (tracked in a small S3 counter object) so a
public, unauthenticated Function URL can't run up Bedrock cost.
"""

import json
import os
import time
from datetime import datetime, timezone

import boto3

OUTPUTS_BUCKET = os.environ["OUTPUTS_BUCKET"]
MODEL_ID = "us.amazon.nova-lite-v1:0"
RATE_LIMIT_KEY = "analysis/checks/_ratelimit.json"
RATE_LIMIT_PER_HOUR = 30

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

SCHEMA_KEYS = {
    "underpass", "drainInletVisible", "inletCondition", "blockage",
    "standingWaterOrStain", "kerbOpeningsVisible", "notes", "framesUsed",
}

QUESTION = """Look at these dashcam frames of one road location. Answer ONLY with a JSON object, no other text, matching exactly this shape:

{
  "underpass": "yes" | "no" | "unclear",
  "drainInletVisible": "yes" | "no" | "unclear",
  "inletCondition": "clear" | "partly blocked" | "blocked" | "not visible",
  "blockage": ["garbage" | "silt" | "vegetation" | "parked vehicle" | "none", ...],
  "standingWaterOrStain": "yes" | "no" | "unclear",
  "kerbOpeningsVisible": "yes" | "no" | "unclear",
  "notes": "one short sentence",
  "framesUsed": [<frame indexes you could actually see clearly>]
}

Answer "unclear" rather than guessing. This is evidence for an engineer to verify in person, not a final judgement."""


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        city = body["city"]
        spot_id = body["spotId"]
        refresh = bool(body.get("refresh", False))
    except (KeyError, json.JSONDecodeError) as e:
        return _response(400, {"error": f"invalid request body: {e}"})

    cache_key = f"analysis/checks/{city}/{spot_id}.json"

    if not refresh:
        cached = _get_json(cache_key)
        if cached is not None:
            return _response(200, cached)

    if not _check_rate_limit():
        return _response(429, {"error": "rate limit: 30 checks/hour reached, try again later"})

    findings = _get_json(f"analysis/findings-{city}.json")
    if findings is None:
        return _response(404, {"error": f"no findings-{city}.json in outputs bucket"})
    spot = next((s for s in findings["spots"] if s["id"] == spot_id), None)
    if spot is None:
        return _response(404, {"error": f"no spot {spot_id} in findings-{city}.json"})

    frames = _collect_frames(spot)
    if not frames:
        return _response(404, {"error": f"no dashcam frames found for spot {spot_id}"})

    result = _ask_model(frames)
    if result is None:
        return _response(502, {"error": "model did not return valid JSON after a retry"})

    result["model"] = MODEL_ID
    result["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    s3.put_object(Bucket=OUTPUTS_BUCKET, Key=cache_key, Body=json.dumps(result), ContentType="application/json")
    return _response(200, result)


def _collect_frames(spot: dict, max_frames: int = 4) -> list[dict]:
    """Best frame first, then up to 3 more from the spot's stretches. Original images,
    not overlays -- the model should see the road as a driver does."""
    out = []
    for stretch in spot.get("stretches", [])[:3]:
        prefix = f"analysis/{stretch['sequenceId']}-lth"
        analysis = _get_json(f"{prefix}/analysis.json")
        if analysis is None:
            continue
        cell = next((c for c in analysis["cells"] if c["id"] == stretch["cellId"]), None)
        if cell is None:
            continue
        for idx in cell["frameIndexes"]:
            frame = next((f for f in analysis["frames"] if f["index"] == idx), None)
            if frame is not None:
                out.append({"index": idx, "key": f"{prefix}/{frame['image']}"})
            if len(out) >= max_frames:
                return out
    return out


def _ask_model(frames: list[dict]) -> dict | None:
    content = [{"text": QUESTION}]
    for f in frames:
        image_bytes = s3.get_object(Bucket=OUTPUTS_BUCKET, Key=f["key"])["Body"].read()
        content.append({"image": {"format": "jpeg", "source": {"bytes": image_bytes}}})

    for attempt in range(2):
        response = bedrock.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": 400, "temperature": 0.0},
        )
        text = response["output"]["message"]["content"][0]["text"].strip()
        parsed = _parse_json(text)
        if parsed is not None and SCHEMA_KEYS.issubset(parsed.keys()):
            return parsed
        content = content + [{"text": "That wasn't valid JSON matching the schema. Answer again, JSON only."}]
    return None


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _check_rate_limit() -> bool:
    now = time.time()
    record = _get_json(RATE_LIMIT_KEY) or {"calls": []}
    recent = [t for t in record["calls"] if now - t < 3600]
    if len(recent) >= RATE_LIMIT_PER_HOUR:
        return False
    recent.append(now)
    s3.put_object(Bucket=OUTPUTS_BUCKET, Key=RATE_LIMIT_KEY, Body=json.dumps({"calls": recent}), ContentType="application/json")
    return True


def _get_json(key: str) -> dict | None:
    try:
        return json.loads(s3.get_object(Bucket=OUTPUTS_BUCKET, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return None


def _response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
