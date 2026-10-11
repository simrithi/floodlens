"""End-to-end run: frames -> perception -> geolocated findings -> risk cells -> analysis.json + images."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from tqdm import tqdm

from . import models
from .analyze import FrameAnalysis, analyze_frame
from .cities import city_for
from .config import DEPTH_REPO, MAX_WORK_WIDTH, OUTPUTS_DIR, POTHOLE_REPO, SEGFORMER_REPO
from .drainage import drainage, export_geojson
from .elevation import dem
from .hydrology import hydrology
from .storms import RETURN_PERIODS, STORM_SOURCES, stations
from .frames import camera_for, load_frames, load_image, sequence_dir
from .segment import own_vehicle_row, segment, sequence_hood_fraction
from .depth import relative_disparity
from .overlay import render_depth, render_overlay, save_jpeg
from .rainfall import rainfall_stats
from .roadprofile import build_profile, frame_index
from .score import build_cells, link_ramps


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
        "kerbs": [
            {
                "side": k.side,
                "beyond": k.beyond,
                "dropCm": None if k.drop_cm is None else round(k.drop_cm, 1),
                "ground": [[round(float(z), 2), round(float(x), 2)] for z, x in k.ground] if k.ground is not None else [],
            }
            for k in a.kerbs
        ],
        "surface": None
        if a.surface is None
        else {
            "camberCm": round(a.surface.camber_cm, 1),
            "crossSlopePct": round(a.surface.cross_slope_pct, 2),
            "gradeChange": round(a.surface.grade_change, 5),
            "rmseCm": round(a.surface.rmse_cm, 2),
        },
        "demElevationM": round(dem_elevation, 1),
    }


def with_hood(camera, frames, sequence_id: int, size: str, max_width: int, samples: int = 15):
    """Camera with the sequence's bonnet cut, measured once on evenly spaced frames (see segment.py)."""
    import dataclasses

    rows, height = [], None
    for f in frames[:: max(1, len(frames) // samples)][:samples]:
        image = load_image(sequence_dir(sequence_id) / size / f.file, max_width)
        height = image.shape[0]
        rows.append(own_vehicle_row(segment(image), relative_disparity(image)))
    share = sequence_hood_fraction(rows, height) if rows else None
    print(f"bonnet: {'none beyond the dashboard' if share is None else f'bottom {share:.0%} of the frame'} (rows {sorted(rows)})")
    return camera if share is None else dataclasses.replace(camera, hood_fraction=share)


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
    c = city_for(frames[0].lat, frames[0].lng)
    camera = with_hood(camera_for(meta), frames, sequence_id, size, max_width)
    terrain = dem(city_key=c.key)
    rain = rainfall_stats(*c.rain_point)

    t0 = time.perf_counter()
    records: list[dict] = []
    work_shape = None
    for f in tqdm(frames, desc=f"analysing {size}", unit="frame"):
        image = load_image(sequence_dir(sequence_id) / size / f.file, max_width)
        work_shape = image.shape[:2]
        a = analyze_frame(f, image, pothole_confidence, camera)
        records.append(frame_record(a, terrain.elevation(f.lat, f.lng)))
        save_jpeg(out_dir / "frames" / f.file, image[:, :, ::-1].copy())
        save_jpeg(out_dir / "overlays" / f.file, render_overlay(image, a))
        depth = render_depth(a)
        if depth is not None:
            save_jpeg(out_dir / "depth" / f.file, depth, quality=80)
    elapsed = time.perf_counter() - t0

    hydro, drains = hydrology(c.key), drainage(c.key)
    export_geojson(c.key)
    profile = road_profile(sequence_id, terrain, records)
    cells = [cell.summary(terrain, hydro, drains, c.key, profile) for cell in build_cells(records)]
    link_ramps(cells, profile)
    analysed = [r for r in records if r["ground"] is not None]
    summary = {
        "frames": len(records),
        "framesWithRoadModel": len(analysed),
        "potholes": sum(len(r["potholes"]) for r in records),
        "dips": sum(len(r["dips"]) for r in records),
        "kerbMeasurements": sum(1 for r in records if r["kerbs"]),
        "cells": len(cells),
        "worstCells": [c["id"] for c in sorted(cells, key=lambda c: -c["risk"])[:5]],
        "seconds": round(elapsed, 1),
        "secondsPerFrame": round(elapsed / max(1, len(records)), 3),
    }
    analysis = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city": {"key": c.key, "name": c.name, "drains": c.drains_name},
        "sequence": {
            "id": sequence_id,
            "source": "KartaView",
            "url": f"https://kartaview.org/details/{sequence_id}",
            "license": "CC BY-SA 4.0",
            "attribution": f"KartaView user #{meta.get('userId', 13451)}",
            "device": meta.get("device", "Xiaomi MI 9"),
            "segments": meta["segments"],
        },
        "input": {"size": size, "workShape": list(work_shape) if work_shape else None, "device": models.device()},
        "camera": {"hfovDeg": camera.hfov_deg, "heightM": camera.height_m, "hoodFraction": round(camera.hood_fraction, 3)},
        "models": {"potholes": POTHOLE_REPO, "segmentation": SEGFORMER_REPO, "depth": DEPTH_REPO, "dem": terrain.kind, "riskModel": "v1 water depth at 2-year storm"},
        "rainfall": rain,
        "designStorms": design_storms(c.key),
        "roadProfile": profile_meta(profile),
        "summary": summary,
        "cells": cells,
        "frames": records,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(json.dumps(analysis, indent=1), encoding="utf-8")
    return analysis


def road_profile(sequence_id: int, terrain, records: list[dict]):
    """Phone-sensor road profile (core/roadprofile.py) if the sequence has a sensor log; adds sagM to frames."""
    path = sequence_dir(sequence_id) / "sensors.txt"
    profile = build_profile(path, terrain) if path.exists() else None
    for r in records:
        i = frame_index(profile, r["index"]) if profile is not None else None
        r["sagM"] = None if i is None else round(float(profile.sag_m[i]), 2)
    return profile


def profile_meta(profile) -> dict | None:
    return None if profile is None else {"source": profile.note, "mountDeg": round(profile.mount_deg, 2)}


def design_storms(city_key: str) -> dict:
    return {
        "source": STORM_SOURCES[city_key],
        "stations": [
            {"name": s.name, "lat": s.lat, "lng": s.lng, "intensityMmHr": {str(t): round(s.intensity(t), 1) for t in RETURN_PERIODS}}
            for s in stations(city_key)
        ],
    }


def rescore(sequence_id: int = 4020141, size: str = "lth", out_dir: Path | None = None) -> dict:
    """Recompute cells and risk from an existing analysis.json, without re-running the neural networks."""
    out_dir = out_dir or OUTPUTS_DIR / f"{sequence_id}-{size}"
    path = out_dir / "analysis.json"
    analysis = json.loads(path.read_text(encoding="utf-8"))
    first = analysis["frames"][0]
    c = city_for(first["lat"], first["lng"])
    terrain, hydro, drains = dem(city_key=c.key), hydrology(c.key), drainage(c.key)
    export_geojson(c.key)
    analysis["city"] = {"key": c.key, "name": c.name, "drains": c.drains_name}
    for r in analysis["frames"]:
        r["demElevationM"] = round(terrain.elevation(r["lat"], r["lng"]), 1)
    profile = road_profile(sequence_id, terrain, analysis["frames"])
    analysis["roadProfile"] = profile_meta(profile)
    cells = [cell.summary(terrain, hydro, drains, c.key, profile) for cell in build_cells(analysis["frames"])]
    link_ramps(cells, profile)
    analysis["cells"] = cells
    analysis["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    analysis["models"]["dem"] = terrain.kind
    analysis["models"]["riskModel"] = "v1 water depth at 2-year storm"
    analysis["designStorms"] = design_storms(c.key)
    analysis["summary"]["worstCells"] = [c["id"] for c in sorted(cells, key=lambda c: -c["risk"])[:5]]
    path.write_text(json.dumps(analysis, indent=1), encoding="utf-8")
    return analysis
