"""Runs after Step Functions' Map state has called the SageMaker endpoint on every
frame and collected their per-frame JSON records. This Lambda does the parts of
pipeline.run() that aren't per-frame: group frames into ~60 m risk cells, score them,
and write the final analysis.json -- exactly the same shape run_local.py produces.

Input (from Step Functions):
  {
    "runId": "...",
    "sequenceId": 4020141,
    "size": "lth",
    "frameRecords": [ ...one dict per frame, each the SageMaker endpoint's response... ]
  }

Writes: s3://<OUTPUTS_BUCKET>/<sequenceId>-<size>/analysis.json
Updates: the floodlens-runs DynamoDB item to status "done" (or "failed").

Does not touch the three deep-learning models at all -- this only imports the
pure-Python parts of core/ (elevation, rainfall, score), so it doesn't need the
SageMaker container's torch/transformers/ultralytics dependencies.
"""

import json
import os
from datetime import datetime, timezone

import boto3

from core.elevation import dem
from core.rainfall import rainfall_stats
from core.score import build_cells

OUTPUTS_BUCKET = os.environ["OUTPUTS_BUCKET"]
RUNS_TABLE = os.environ["RUNS_TABLE"]

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(RUNS_TABLE)


def handler(event, context):
    run_id = event["runId"]
    sequence_id = event["sequenceId"]
    size = event["size"]
    records = event["frameRecords"]

    try:
        terrain = dem()
        rain = rainfall_stats()

        cells = [c.summary(terrain, rain["p99WetHourMm"]) for c in build_cells(records)]
        analysed = [r for r in records if r["ground"] is not None]

        analysis = {
            "version": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input": {"size": size},
            "rainfall": rain,
            "summary": {
                "frames": len(records),
                "framesWithRoadModel": len(analysed),
                "potholes": sum(len(r["potholes"]) for r in records),
                "dips": sum(len(r["dips"]) for r in records),
                "kerbMeasurements": sum(1 for r in records if r["kerb"]),
                "cells": len(cells),
                "worstCells": [c["id"] for c in sorted(cells, key=lambda c: -c["risk"])[:5]],
            },
            "cells": cells,
            "frames": records,
        }

        out_prefix = f"{sequence_id}-{size}"
        s3.put_object(
            Bucket=OUTPUTS_BUCKET,
            Key=f"{out_prefix}/analysis.json",
            Body=json.dumps(analysis, indent=1),
            ContentType="application/json",
        )

        table.update_item(
            Key={"runId": run_id},
            UpdateExpression="SET #s = :s, outputPrefix = :p, completedAt = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "done",
                ":p": out_prefix,
                ":t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        return {"runId": run_id, "status": "done", "cells": len(cells)}

    except Exception as e:
        table.update_item(
            Key={"runId": run_id},
            UpdateExpression="SET #s = :s, errorMessage = :e",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "failed", ":e": str(e)},
        )
        raise
