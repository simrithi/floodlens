"""Lambda behind a Function URL: hands the frontend a presigned S3 PUT URL for uploading
raw footage, plus a new runId. Does not touch the analysis pipeline at all.

Request (POST, JSON body): { "fileName": "drive.mp4", "contentType": "video/mp4" }
Response: { "runId": "...", "uploadUrl": "https://...", "s3Key": "uploads/<runId>/<fileName>" }

The frontend PUTs the file directly to uploadUrl. Nothing here starts the pipeline --
that's triggered separately by the S3 upload event (EventBridge -> Step Functions).
"""

import json
import os
import uuid

import boto3

RAW_BUCKET = os.environ["RAW_BUCKET"]
URL_EXPIRY_SECONDS = 900  # 15 minutes to actually perform the upload

s3 = boto3.client("s3")


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        file_name = body["fileName"]
        content_type = body.get("contentType", "application/octet-stream")
    except (KeyError, json.JSONDecodeError) as e:
        return _response(400, {"error": f"invalid request body: {e}"})

    run_id = str(uuid.uuid4())
    s3_key = f"uploads/{run_id}/{file_name}"

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": RAW_BUCKET, "Key": s3_key, "ContentType": content_type},
        ExpiresIn=URL_EXPIRY_SECONDS,
    )

    return _response(200, {"runId": run_id, "uploadUrl": upload_url, "s3Key": s3_key})


def _response(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
