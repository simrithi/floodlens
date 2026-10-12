"""Called once per frame inside Step Functions' Map state. Thin wrapper around the
SageMaker endpoint: builds the JSON body serve/handler.py expects, invokes the
endpoint synchronously, and returns the parsed per-frame record. Kept as its own
Lambda (rather than hand-building the invoke in Step Functions' native SDK
integration JSON) because the request body is non-trivial and this is far easier
to test and debug as normal Python.

Input (one Map iteration's item, merged with the run-level fields Step Functions
passes alongside it):
  {
    "frame": {...one entry from frames.json...},
    "rawBucket": "...", "rawPrefix": "kartaview/<seq>/<size>",
    "outputBucket": "...", "outputPrefix": "<seq>-<size>",
    "potholeConfidence": 0.35, "maxWidth": 1920
  }

Output: a small pointer {"s3Key": ...} to the full per-frame record, which is written to
s3://<outputBucket>/<outputPrefix>/frame-records/<file>.json. Step Functions caps a state's result at
256 KB, which a Map over a few hundred frames exceeds if it carries the full records; assemble-results
reads the records back from S3.
"""

import json

import boto3

sm = boto3.client("sagemaker-runtime")
s3 = boto3.client("s3")

ENDPOINT_NAME = "floodlens-analyze"


def handler(event, context):
    frame = event["frame"]
    image_s3_uri = f"s3://{event['rawBucket']}/{event['rawPrefix']}/{frame['file']}"

    body = {
        "image_s3_uri": image_s3_uri,
        "frame": frame,
        "pothole_confidence": event.get("potholeConfidence", 0.35),
        "max_width": event.get("maxWidth", 1920),
        "output_bucket": event["outputBucket"],
        "output_prefix": event["outputPrefix"],
    }

    response = sm.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps(body),
    )
    record = json.loads(response["Body"].read())
    key = f"{event['outputPrefix']}/frame-records/{frame['file']}.json"
    s3.put_object(Bucket=event["outputBucket"], Key=key, Body=json.dumps(record), ContentType="application/json")
    return {"s3Key": key}
