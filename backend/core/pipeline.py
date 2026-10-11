"""End-to-end run: frames -> perception -> geolocated findings -> risk cells -> analysis.json + images."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from tqdm import tqdm

from . import models
from .analyze import FrameAnalysis, analyze_frame
from .config import CAMERA, DEPTH_REPO, MAX_WORK_WIDTH, OUTPUTS_DIR, POTHOLE_REPO, SEGFORMER_REPO, DEM_TILE
from .elevation import dem
from .frames import load_frames, load_image, sequence_dir
from .overlay import render_depth, render_overlay, save_jpeg
from .rainfall import rainfall_stats
from .score import build_cells


def frame_record(a: FrameAnalysis, dem_elevation: float) -> dict:
    f = a.frame
    potholes = []
    for p, depth in zip(a.potholes, a.pothole_depth_cm):
        ys, _ = np.nonzero(p.mask)
        area = float(np.nansum(a.ground.pixel_area_m2(ys))) if a.ground is not None and ys.size else None
        pos = a.locate((p.bbox[0] + p.bbox[2]) / 2, p.bbox[3])
        potholes.append(
            {
                "confidence": round(p.confidence, 3),
                "bbox": list(p.bbox),
                "depthCm": round(depth, 1),
                "areaM2": round(area, 2) if area is not None and np.isfinite(area) else 0.0,
                "lat": round(pos[0], 7) if pos else None,
                "lng": round(pos[1], 7) if pos else None,
            }
        )
    dips = []
    for d in a.dips:
        pos = a.locate(*d.centroid)
        dips.append(
            {
                "depthCm": round(d.depth_cm, 1),
                "areaM2": round(d.area_m2, 2),
                "distanceM": round(d.distance_m, 1),
                "lat": round(pos[0], 7) if pos else None,
                "lng": round(pos[1], 7) if pos else None,
            }
        )
    return {
        "index": f.index,
        "segment": f.segment,
        "lat": f.lat,
        "lng": f.lng,
        "heading": f.heading,
        "shotDate": f.shot_date,
        "image": f"frames/{f.file}",
        "overlay": f"overlays/{f.file}",
        "depth": f"depth/{f.file}",
        "roadFraction": round(a.road_fraction, 3),
        "ground": None
        if a.ground is None
        else {"horizonY": round(a.ground.horizon_y, 1), "inliers": a.ground.inliers, "residualStd": round(a.ground.residual_std, 4)},
        "potholes": potholes,
        "dips": dips,
        "kerb": None if a.kerb is None else {"dropCm": round(a.kerb.drop_cm, 1), "side": a.kerb.side},
        "demElevationM": round(dem_elevation, 1),
    }


def run(
    sequence_id: int = 4020141,
    size: str = "lth",
    segments: list[str] | None = None,
    limit: int | None = None,
    out_dir: Path | None = None,
    pothole_confidence: float = 0.35,
    max_width: int = MAX_WORK_WIDTH,
) -> dict:
    out_dir = out_dir or OUTPUTS_DIR / f"{sequence_id}-{size}"
    meta, frames = load_frames(sequence_id, segments)
    if limit:
        frames = frames[:limit]
    terrain = dem()
    rain = rainfall_stats()

    t0 = time.perf_counter()
    records: list[dict] = []
    work_shape = None
    for f in tqdm(frames, desc=f"analysing {size}", unit="frame"):
        image = load_image(sequence_dir(sequence_id) / size / f.file, max_width)
        work_shape = image.shape[:2]
        a = analyze_frame(f, image, pothole_confidence)
        records.append(frame_record(a, terrain.elevation(f.lat, f.lng)))
        save_jpeg(out_dir / "frames" / f.file, image[:, :, ::-1].copy())
        save_jpeg(out_dir / "overlays" / f.file, render_overlay(image, a))
        depth = render_depth(a)
        if depth is not None:
            save_jpeg(out_dir / "depth" / f.file, depth, quality=80)
    elapsed = time.perf_counter() - t0

    cells = [c.summary(terrain, rain["p99WetHourMm"]) for c in build_cells(records)]
    analysed = [r for r in records if r["ground"] is not None]
    summary = {
        "frames": len(records),
        "framesWithRoadModel": len(analysed),
        "potholes": sum(len(r["potholes"]) for r in records),
        "dips": sum(len(r["dips"]) for r in records),
        "kerbMeasurements": sum(1 for r in records if r["kerb"]),
        "cells": len(cells),
        "worstCells": [c["id"] for c in sorted(cells, key=lambda c: -c["risk"])[:5]],
        "seconds": round(elapsed, 1),
        "secondsPerFrame": round(elapsed / max(1, len(records)), 3),
    }
    analysis = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sequence": {
            "id": sequence_id,
            "source": "KartaView",
            "url": f"https://kartaview.org/details/{sequence_id}",
            "license": "CC BY-SA 4.0",
            "attribution": "KartaView user #13451",
            "segments": meta["segments"],
        },
        "input": {"size": size, "workShape": list(work_shape) if work_shape else None, "device": models.device()},
        "camera": {"hfovDeg": CAMERA.hfov_deg, "heightM": CAMERA.height_m},
        "models": {"potholes": POTHOLE_REPO, "segmentation": SEGFORMER_REPO, "depth": DEPTH_REPO, "dem": DEM_TILE},
        "rainfall": rain,
        "summary": summary,
        "cells": cells,
        "frames": records,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(json.dumps(analysis, indent=1), encoding="utf-8")
    return analysis
