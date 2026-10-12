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
pure-Python parts of core/ (elevation, rainfall, score, cities, hydrology,
drainage), so it doesn't need the SageMaker container's
torch/transformers/ultralytics dependencies.

Risk model: v1, physical water depth at a 2-year design storm (core/waterdepth.py),
replacing the old rainfall-percentile heuristic. Cell.summary() needs a Hydrology
and a Drainage object, both keyed by city -- city_for() picks the city from the
frames' own coordinates, so this works for any surveyed city, not just Delhi.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import boto3

from core.cities import city_for
from core.config import GEO_DIR
from core.drainage import drainage
from core.elevation import dem
from core.hydrology import hydrology
from core.rainfall import rainfall_stats
from core.score import build_cells

OUTPUTS_BUCKET = os.environ["OUTPUTS_BUCKET"]
RUNS_TABLE = os.environ["RUNS_TABLE"]


def _load_record(item):
    """invoke-frame returns a pointer to the full record (Step Functions' 256 KB state limit);
    older runs passed the record inline, so accept both."""
    if "s3Key" in item and "ground" not in item:
        body = boto3.client("s3").get_object(Bucket=OUTPUTS_BUCKET, Key=item["s3Key"])["Body"].read()
        return json.loads(body)
    return item


# Mirrors scripts/fetch_kartaview.py's SEGMENTS + ATTRIBUTION.md for the sequences this
# project surveys. build_findings.py needs this (sequence id, named segment labels, and
# licence attribution) alongside the per-frame records; it isn't in frameRecords itself.
SEQUENCE_META = {
    4020141: {
        "device": "Xiaomi MI 9",
        "date": "2021-12-21",
        "segments": [
            {"name": "ito", "label": "ITO crossing approach"},
            {"name": "minto", "label": "Minto Bridge underpass"},
        ],
    },
    3827609: {
        "device": "unknown KartaView contributor device",
        "date": "2021-09",
        "segments": [
            {"name": "orr-south", "label": "ORR Marathahalli to Kadubeesanahalli (southbound)"},
            {"name": "orr-north", "label": "ORR Kadubeesanahalli to Marathahalli (northbound)"},
        ],
    },
    9316057: {
        "device": "unknown KartaView contributor device",
        "date": "2024-08",
        "segments": [
            {"name": "bellandur", "label": "Bellandur, ORR side roads"},
        ],
    },
}


def _sequence_block(sequence_id: int) -> dict:
    meta = SEQUENCE_META.get(sequence_id, {"device": "unknown", "date": "unknown", "segments": []})
    return {
        "id": sequence_id,
        "url": f"https://kartaview.org/details/{sequence_id}",
        "attribution": (
            f"Imagery: KartaView sequence {sequence_id}, recorded {meta['date']} on a {meta['device']}, "
            "licensed CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)."
        ),
        "segments": meta["segments"],
    }

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(RUNS_TABLE)


def _seed_hydrology() -> None:
    """Copy the pre-built hydrology rasters from the image's read-only bundle into /tmp at
    cold start, for every city baked in. Lambda gives each execution environment a fresh
    /tmp -- anything baked into /tmp at image build time is not what the running container
    sees, so this has to happen here, once, the first time this module loads in a given
    environment."""
    for seed_name, dest in (("hydro-delhi", GEO_DIR / "hydro"), ("hydro-bengaluru", GEO_DIR / "bengaluru" / "hydro")):
        seed = Path("seed") / seed_name
        if not seed.exists() or (dest / "twi.tif").exists():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for f in seed.glob("*.tif"):
            shutil.copy(f, dest / f.name)
    # Official drain network for Bengaluru (KSRSAC 2022, converted from OpenCity's KML): core/drainage.py reads it.
    drains = Path("seed") / "geo-bengaluru"
    if drains.exists():
        (GEO_DIR / "bengaluru").mkdir(parents=True, exist_ok=True)
        for f in drains.glob("*.json"):
            if not (GEO_DIR / "bengaluru" / f.name).exists():
                shutil.copy(f, GEO_DIR / "bengaluru" / f.name)


_seed_hydrology()


def handler(event, context):
    run_id = event["runId"]
    sequence_id = event["sequenceId"]
    size = event["size"]
    records = [_load_record(r) for r in event["frameRecords"]]

    try:
        first = records[0]
        c = city_for(first["lat"], first["lng"])
        terrain = dem(city_key=c.key)
        hydro = hydrology(c.key)
        drains = drainage(c.key)
        rain = rainfall_stats()

        cells = [cell.summary(terrain, hydro, drains, c.key) for cell in build_cells(records)]
        analysed = [r for r in records if r["ground"] is not None]

        analysis = {
            "version": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sequence": _sequence_block(sequence_id),
            "city": {"key": c.key, "name": c.name, "drains": c.drains_name},
            "input": {"size": size},
            "models": {"riskModel": "v1 water depth at 2-year storm"},
            "rainfall": rain,
            "summary": {
                "frames": len(records),
                "framesWithRoadModel": len(analysed),
                "potholes": sum(len(r["potholes"]) for r in records),
                "dips": sum(len(r["dips"]) for r in records),
                "kerbMeasurements": sum(1 for r in records if r["kerbs"]),
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
