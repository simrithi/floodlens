"""SageMaker inference container entry point.

Wraps core.analyze.analyze_frame for exactly one dashcam frame: downloads the
frame image from S3, runs segmentation + depth + pothole detection + geometry
(unchanged, imported straight from core/), writes the overlay and depth images
to the outputs bucket, and returns the same per-frame JSON shape
pipeline.frame_record() already produces locally. Nothing in core/ is modified;
this file only calls it.

Contract (standard SageMaker custom-container contract, also what Async
Inference uses under the hood):
  GET  /ping          liveness check, must return 200
  POST /invocations   application/json in, application/json out

Expected input:
  {
    "image_s3_uri": "s3://floodlens-raw-.../4020141/lth/0519.jpg",
    "frame": {
      "index": 519, "id": 123456, "segment": "ito",
      "lat": 28.62, "lng": 77.24, "heading": 184.1,
      "shotDate": "2021-12-21 08:28:00.000", "file": "0519.jpg"
    },
    "pothole_confidence": 0.35,
    "max_width": 1920,
    "output_bucket": "floodlens-outputs-...",
    "output_prefix": "4020141-lth"
  }

Output: one entry of analysis.json's "frames" array (see docs/APPLICATION.md
section 9), minus nothing -- demElevationM is filled in here too, since the
DEM lookup is cheap and keeping one frame's record complete in one response
is simpler than splitting it across two network hops.
"""

import json
import logging
import tempfile
from pathlib import Path

import boto3
import cv2
from flask import Flask, Response, request

from core.analyze import analyze_frame
from core.cities import city_for
from core.elevation import dem
from core.frames import Frame, load_image
from core.overlay import render_depth, render_overlay
from core.pipeline import frame_record

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("floodlens.serve")

app = Flask(__name__)
s3 = boto3.client("s3")


@app.get("/ping")
def ping() -> Response:
    return Response(status=200)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"not an s3:// uri: {uri}")
    bucket, _, key = uri[len("s3://") :].partition("/")
    return bucket, key


def _put_jpeg(bucket: str, key: str, bgr, quality: int = 86) -> None:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError(f"failed to encode {key}")
    s3.put_object(Bucket=bucket, Key=key, Body=buf.tobytes(), ContentType="image/jpeg")


@app.post("/invocations")
def invocations() -> Response:
    body = request.get_json(force=True)
    fr = body["frame"]
    frame = Frame(
        index=fr["index"],
        id=fr["id"],
        segment=fr["segment"],
        lat=fr["lat"],
        lng=fr["lng"],
        heading=fr.get("heading"),
        shot_date=fr["shotDate"],
        file=fr["file"],
    )
    confidence = float(body.get("pothole_confidence", 0.35))
    max_width = int(body.get("max_width", 1920))
    out_bucket = body["output_bucket"]
    out_prefix = body["output_prefix"].rstrip("/")

    log.info("analysing frame %s (%s)", frame.index, frame.file)
    src_bucket, src_key = _parse_s3_uri(body["image_s3_uri"])
    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / frame.file
        s3.download_file(src_bucket, src_key, str(local_path))
        image = load_image(local_path, max_width)

    analysis = analyze_frame(frame, image, confidence)

    overlay = render_overlay(image, analysis)
    _put_jpeg(out_bucket, f"{out_prefix}/overlays/{frame.file}", overlay)
    depth_img = render_depth(analysis)
    if depth_img is not None:
        _put_jpeg(out_bucket, f"{out_prefix}/depth/{frame.file}", depth_img, quality=80)
    _put_jpeg(out_bucket, f"{out_prefix}/frames/{frame.file}", image[:, :, ::-1])

    city_key = city_for(frame.lat, frame.lng).key
    elevation_m = dem(city_key=city_key).elevation(frame.lat, frame.lng)
    record = frame_record(analysis, elevation_m)
    log.info("frame %s done: %d potholes, %d dips", frame.index, len(record["potholes"]), len(record["dips"]))
    return Response(json.dumps(record), mimetype="application/json")


if __name__ == "__main__":
    # Local/dev run only. The container's real start command (Dockerfile) uses gunicorn.
    app.run(host="0.0.0.0", port=8080)
