"""Behind a Function URL. Lets an officer approve a tomorrow-alert action, and lets
anyone report what actually happened on the ground -- closing the loop between a
prediction and reality, so scripts/compare_observations.py has something to check
predictions against.

POST (write, passcode required): {
  "passcode": "...",
  "city": "delhi", "spotId": "S2",
  "kind": "approval" | "observation",
  # approval:
  "approved": true, "note": "...",
  # observation:
  "flooded": true, "depthCm": 12, "date": "2026-10-11", "photoKey": "..."  (depthCm/photoKey optional)
}

GET (read, no passcode): ?city=delhi -- lists every action/observation for that city,
newest first.

The passcode is an SSM SecureString (/floodlens/officer-passcode) the user sets
themselves in the console -- this Lambda never prints or logs its value, and
refuses all writes until it's actually set to something.
"""

import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal

import boto3

TABLE_NAME = os.environ["ACTIONS_TABLE"]
PASSCODE_PARAM = "/floodlens/officer-passcode"

table = boto3.resource("dynamodb").Table(TABLE_NAME)
ssm = boto3.client("ssm")

CITY_RE = re.compile(r"^[a-z]+$")
SPOT_RE = re.compile(r"^S\d+$")


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "GET":
        return _list(event)
    return _record(event)


def _list(event):
    city = (event.get("queryStringParameters") or {}).get("city")
    if not city or not CITY_RE.match(city):
        return _response(400, {"error": "missing or invalid ?city="})

    # pk is "<city>#<spotId>", not wildcard-queryable directly -- scan-filter instead.
    # Fine at this table's expected size (one hackathon's worth of actions); a GSI on
    # city would be the real fix if this ever needs to scale.
    items = table.scan(
        FilterExpression="begins_with(pk, :prefix)",
        ExpressionAttributeValues={":prefix": f"{city}#"},
    ).get("Items", [])
    items.sort(key=lambda i: i["sk"], reverse=True)
    return _response(200, {"city": city, "items": items})


def _record(event):
    try:
        body = json.loads(event.get("body") or "{}")
        passcode = body["passcode"]
        city = body["city"]
        spot_id = body["spotId"]
        kind = body["kind"]
        if kind not in ("approval", "observation"):
            return _response(400, {"error": "kind must be 'approval' or 'observation'"})
        if not CITY_RE.match(city) or not SPOT_RE.match(spot_id):
            return _response(400, {"error": "invalid city or spotId"})
    except (KeyError, json.JSONDecodeError) as e:
        return _response(400, {"error": f"invalid request body: {e}"})

    if not _check_passcode(passcode):
        return _response(401, {"error": "wrong or unset passcode"})

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    item = {
        "pk": f"{city}#{spot_id}",
        "sk": f"{now}#{kind}",
        "city": city,
        "spotId": spot_id,
        "kind": kind,
        "recordedAt": now,
    }

    if kind == "approval":
        if "approved" not in body:
            return _response(400, {"error": "approval needs 'approved': true|false"})
        item["approved"] = bool(body["approved"])
        item["note"] = str(body.get("note", ""))
    else:
        if "flooded" not in body:
            return _response(400, {"error": "observation needs 'flooded': true|false"})
        item["flooded"] = bool(body["flooded"])
        item["date"] = body.get("date", now[:10])
        if body.get("depthCm") is not None:
            item["depthCm"] = Decimal(str(body["depthCm"]))
        if body.get("photoKey"):
            item["photoKey"] = str(body["photoKey"])

    table.put_item(Item=item)
    return _response(200, {"recorded": True, "pk": item["pk"], "sk": item["sk"]})


def _check_passcode(given: str) -> bool:
    try:
        real = ssm.get_parameter(Name=PASSCODE_PARAM, WithDecryption=True)["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        return False
    return bool(real) and given == real


def _response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }
