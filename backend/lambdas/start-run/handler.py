"""Triggered by EventBridge when a sequence's frames.json lands in the raw S3 bucket
(kartaview/<sequenceId>/frames.json -- shared across both image sizes, matching
scripts/fetch_kartaview.py's real layout). Reads the manifest, creates the run's
DynamoDB row, and starts the Step Functions execution that processes every frame.

Always processes the "lth" (1280p) size -- the same default the UI itself uses
(state.tsx: useState<Run>('lth')). Trigger a "full" (4K) run manually via
stepfunctions:StartExecution if needed; frames.json doesn't indicate a size since
it's the same file for both.

Does not touch the deep-learning models or core/ at all -- just S3, DynamoDB and
Step Functions, so this is a plain Lambda, no container needed.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

RUNS_TABLE = os.environ["RUNS_TABLE"]
OUTPUTS_BUCKET = os.environ["OUTPUTS_BUCKET"]
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]
SIZE = "lth"

# kartaview/<sequenceId>/frames.json
KEY_PATTERN = re.compile(r"^kartaview/(\d+)/frames\.json$")

s3 = boto3.client("s3")
sfn = boto3.client("stepfunctions")
table = boto3.resource("dynamodb").Table(RUNS_TABLE)


def handler(event, context):
    detail = event["detail"]
    bucket = detail["bucket"]["name"]
    key = detail["object"]["key"]

    m = KEY_PATTERN.match(key)
    if not m:
        print(f"ignoring upload, doesn't match kartaview/<seq>/frames.json: {key}")
        return {"skipped": key}
    sequence_id = int(m.group(1))

    manifest = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    frames = manifest["frames"]

    run_id = str(uuid.uuid4())
    raw_prefix = f"kartaview/{sequence_id}/{SIZE}"
    output_prefix = f"{sequence_id}-{SIZE}"

    table.put_item(
        Item={
            "runId": run_id,
            "status": "processing",
            "sequenceId": sequence_id,
            "size": SIZE,
            "frameCount": len(frames),
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )

    sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=f"run-{run_id}",
        input=json.dumps(
            {
                "runId": run_id,
                "sequenceId": sequence_id,
                "size": SIZE,
                "rawBucket": bucket,
                "rawPrefix": raw_prefix,
                "outputBucket": OUTPUTS_BUCKET,
                "outputPrefix": output_prefix,
                "frames": frames,
            }
        ),
    )

    return {"runId": run_id, "frames": len(frames)}
