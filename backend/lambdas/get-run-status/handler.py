"""Lambda behind a Function URL: the frontend polls this to see whether a run is
still processing or done. Just a DynamoDB read, nothing else.

Request: GET ?runId=<uuid>
Response: the floodlens-runs item for that runId, or 404 if it doesn't exist yet.
"""

import json
import os

import boto3

TABLE_NAME = os.environ["RUNS_TABLE"]

table = boto3.resource("dynamodb").Table(TABLE_NAME)


def handler(event, context):
    run_id = (event.get("queryStringParameters") or {}).get("runId")
    if not run_id:
        return _response(400, {"error": "missing runId query parameter"})

    item = table.get_item(Key={"runId": run_id}).get("Item")
    if item is None:
        return _response(404, {"error": "no such run"})

    return _response(200, item)


def _response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }
