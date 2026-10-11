"""Validation against publicly reported Delhi waterlogging hotspots.

Two checks, because the dashcam has only covered a few kilometres so far:

A. City-wide terrain check. The terrain factor (DEM height vs. the surrounding 400 m) is the part of
   the risk score that exists everywhere. Do reported hotspots sit lower than ordinary main roads?
   Controls are random points on OpenStreetMap trunk/primary/secondary roads in Delhi, at least
   500 m from any reported hotspot.

B. Dashcam stretch check. For the measured ~60 m road cells: are the cells near a reported hotspot
   (within 300 m) scored higher than the rest, and how many of the top-scored cells are near one?

Reference data: validation/reference_hotspots.geo.json (compiled from public PWD / Traffic Police
announcements and storm reports; not the complete official list, which is not published).
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .config import BACKEND_DIR, GEO_DIR, OUTPUTS_DIR
from .elevation import dem
from .drainage import drainage
from .hydrology import hydrology
from .waterdepth import predict
from .osmtiles import fetch_lines
from .score import distance_m

REFERENCE = BACKEND_DIR / "validation" / "reference_hotspots.geo.json"
MAIN_ROAD_CLASSES = {"trunk", "primary", "secondary"}
TERRAIN_HIT_M = -1.0  # "low ground": at least 1 m below the surrounding 400 m (terrain factor >= 0.4)
CELL_NEAR_M = 300
RISK_HIGH = 50


def load_reference() -> dict:
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def main_roads() -> list[list[tuple[float, float]]]:
    """Trunk/primary/secondary road polylines in Delhi from OpenStreetMap (cached in data/geo/)."""
    lines = fetch_lines("transportation", MAIN_ROAD_CLASSES, GEO_DIR / "osm_main_roads_delhi_v2.json")
    return [[tuple(p) for p in w["coords"]] for w in lines]


def sample_controls(hotspots: list[tuple[float, float]], n: int = 400, min_gap_m: float = 500, seed: int = 7) -> list[tuple[float, float]]:
    """Random points on main roads, uniform by road length, away from reported hotspots and inside the DEM tile."""
    terrain = dem()
    segments = []
    for way in main_roads():
        for a, b in zip(way, way[1:]):
            segments.append((a, b, distance_m(a, b)))
    lengths = np.array([s[2] for s in segments])
    probs = lengths / lengths.sum()
    rng = np.random.default_rng(seed)
    out: list[tuple[float, float]] = []
    while len(out) < n:
        a, b, _ = segments[rng.choice(len(segments), p=probs)]
        t = rng.random()
        p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if terrain.contains(*p) and all(distance_m(p, h) >= min_gap_m for h in hotspots):
            out.append(p)
    return out


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Probability that a random positive scores higher than a random negative (ties count half)."""
    diff = pos[:, None] - neg[None, :]
    return float((diff > 0).mean() + 0.5 * (diff == 0).mean())


def bootstrap_ci(pos: np.ndarray, neg: np.ndarray, stat, n: int = 2000, seed: int = 11) -> tuple[float, float]:
    """95% percentile bootstrap interval of stat(pos, neg), resampling both groups."""
    rng = np.random.default_rng(seed)
    vals = [stat(rng.choice(pos, pos.size), rng.choice(neg, neg.size)) for _ in range(n)]
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return round(float(lo), 3), round(float(hi), 3)


def terrain_check(ref: dict, kind: str | None = None) -> dict:
    terrain = dem(kind)
    hs = [h for h in ref["hotspots"] if h["lat"] is not None]
    points = [(h["lat"], h["lng"]) for h in hs]
    rel_h = np.array([terrain.relative(*p) for p in points])
    controls = sample_controls(points)
    rel_c = np.array([terrain.relative(*p) for p in controls])
    hit_h = float((rel_h <= TERRAIN_HIT_M).mean())
    hit_c = float((rel_c <= TERRAIN_HIT_M).mean())
    return {
        "dem": terrain.kind,
        "hotspots": len(points),
        "controls": len(controls),
        "lowGroundThresholdM": TERRAIN_HIT_M,
        "hitRate": round(hit_h, 3),
        "controlRate": round(hit_c, 3),
        "lift": round(hit_h / hit_c, 2) if hit_c else None,
        "auc": round(auc(-rel_h, -rel_c), 3),
        "aucCi95": bootstrap_ci(-rel_h, -rel_c, auc),
        "hitRateCi95": bootstrap_ci(rel_h, rel_c, lambda p, n: float((p <= TERRAIN_HIT_M).mean())),
        "medianRelativeHotspotsM": round(float(np.median(rel_h)), 2),
        "medianRelativeControlsM": round(float(np.median(rel_c)), 2),
        "controlsRelativeM": [round(float(r), 2) for r in rel_c],
        "perHotspot": [
            {"id": h["id"], "name": h["name"], "relativeM": round(float(r), 2), "lowGround": bool(r <= TERRAIN_HIT_M)}
            for h, r in zip(hs, rel_h)
        ],
    }


HYDRO_RADIUS_M = 60  # fixed before looking at results; 30 m and 120 m were checked only for sensitivity


def hydro_check(ref: dict) -> dict:
    """Water-flow features on bare earth: do hotspots sit in hollows / at the bottom of large catchments?"""
    h = hydrology()
    hs = [x for x in ref["hotspots"] if x["lat"] is not None and h.contains(x["lat"], x["lng"])]
    points = [(x["lat"], x["lng"]) for x in hs]
    controls = [p for p in sample_controls(points) if h.contains(*p)]
    dr = drainage()
    def features_at(p: tuple[float, float]) -> dict:
        d = h.sample(*p, radius_m=HYDRO_RADIUS_M) | {"drainM": dr.nearest(*p)["distanceM"]}
        d["depth2y"] = predict(*p, d, dr.capacity_mm_hr(d["drainM"]))["designStorms"][0]["depthCm"]
        return d

    hot = [features_at(p) for p in points]
    ctl = [features_at(p) for p in controls]
    features = {
        "depression": ("Sits in a hollow (depth, m)", lambda d: d["depression"]),
        "upstream": ("Land draining here (log10 m2)", lambda d: math.log10(d["upstream"] + 1)),
        "twi": ("Wetness index", lambda d: d["twi"]),
        "drainDistance": ("Distance to nearest mapped drain (log10 m)", lambda d: math.log10(d["drainM"] + 1)),
        "depth2y": ("Predicted water at a 2-year storm (cm, terrain + drains only)", lambda d: d["depth2y"]),
    }
    out = {"radiusM": HYDRO_RADIUS_M, "hotspots": len(points), "controls": len(controls), "features": {}}
    for key, (label, f) in features.items():
        a = np.array([f(d) for d in hot])
        b = np.array([f(d) for d in ctl])
        out["features"][key] = {
            "label": label,
            "auc": round(auc(a, b), 3),
            "aucCi95": bootstrap_ci(a, b, auc),
            "medianHotspots": round(float(np.median(a)), 3),
            "medianControls": round(float(np.median(b)), 3),
        }
    out["perHotspot"] = [
        {"id": x["id"], "depressionM": round(d["depression"], 2), "upstreamM2": round(d["upstream"]), "twi": round(d["twi"], 2), "drainM": round(d["drainM"]), "depth2yCm": d["depth2y"]}
        for x, d in zip(hs, hot)
    ]
    return out


def cell_check(ref: dict, analysis_path: Path) -> dict | None:
    if not analysis_path.exists():
        return None
    a = json.loads(analysis_path.read_text(encoding="utf-8"))
    hs = [h for h in ref["hotspots"] if h["lat"] is not None]
    cells = []
    for c in a["cells"]:
        near = min(hs, key=lambda h: distance_m((c["lat"], c["lng"]), (h["lat"], h["lng"])))
        d = distance_m((c["lat"], c["lng"]), (near["lat"], near["lng"]))
        cells.append({"id": c["id"], "risk": c["risk"], "nearest": near["id"], "nearestName": near["name"], "distanceM": round(d), "near": d <= CELL_NEAR_M})
    pos = np.array([c["risk"] for c in cells if c["near"]])
    neg = np.array([c["risk"] for c in cells if not c["near"]])
    top = sorted(cells, key=lambda c: -c["risk"])[:5]
    covered = sorted({c["nearest"] for c in cells if c["near"]})
    return {
        "run": a["input"]["size"],
        "cells": len(cells),
        "cellsNearHotspot": int(len(pos)),
        "hotspotsCovered": [{"id": i, "name": next(h["name"] for h in hs if h["id"] == i)} for i in covered],
        "meanRiskNear": round(float(pos.mean()), 1) if pos.size else None,
        "meanRiskOther": round(float(neg.mean()), 1) if neg.size else None,
        "highRiskNear": round(float((pos >= RISK_HIGH).mean()), 3) if pos.size else None,
        "highRiskOther": round(float((neg >= RISK_HIGH).mean()), 3) if neg.size else None,
        "precisionTop5": round(sum(c["near"] for c in top) / len(top), 2) if top else None,
        "auc": round(auc(pos, neg), 3) if pos.size and neg.size else None,
        "nearRadiusM": CELL_NEAR_M,
        "highRiskThreshold": RISK_HIGH,
        "perCell": cells,
    }


def run(sequence_id: int = 4020141) -> dict:
    ref = load_reference()
    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference": {
            "description": ref["description"],
            "count": len(ref["hotspots"]),
            "sources": ref["sources"],
            "points": [
                {"id": h["id"], "name": h["name"], "lat": h["lat"], "lng": h["lng"], "sources": h["sources"], "approximate": h["geocoded"].startswith("manual")}
                for h in ref["hotspots"]
            ],
        },
        "terrain": terrain_check(ref),
        "terrainSurface": terrain_check(ref, "surface"),
        "hydrology": hydro_check(ref),
        "cells": {size: cell_check(ref, OUTPUTS_DIR / f"{sequence_id}-{size}" / "analysis.json") for size in ("lth", "full")},
        "caveats": [
            "Reference set is 36 publicly named hotspots, not the full official list (445 points in 2025).",
            "Hotspot coordinates are geocoded from names (about +-150 m); 7 were placed by hand.",
            "Terrain uses FABDEM bare earth (buildings and trees removed) on a 30 m grid; narrow features such as underpasses are below its resolution.",
            "Dashcam coverage is two stretches (~2.5 km), so the stretch check has very few samples.",
        ],
    }
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / "validation.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result
