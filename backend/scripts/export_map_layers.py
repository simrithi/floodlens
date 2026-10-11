"""Export map layers for the UI from real data (no sample values).

Writes to data/outputs/:
  hollows.png / hollows.json   (hollows-<city>.* for cities other than Delhi) bare-earth hollows as a transparent image with its geographic corners, for a
                               MapLibre image source. Only hollows deeper than 1 m and at least 4 cells (~0.33 ha)
                               are shown: FABDEM's vertical error in built-up areas is a few metres, so shallower
                               or single-cell hollows are mostly noise. The water model still uses the full layer.
  route_profile.json           bare-earth elevation, hollow depth and dashcam coverage along the demo route (Delhi)
  drains.geojson               OpenStreetMap drainage network (drains-<city>.geojson elsewhere)

usage: python scripts/export_map_layers.py [--city delhi|bengaluru]
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cities import CITIES  # noqa: E402
from core.config import OUTPUTS_DIR, PROJECT_DIR  # noqa: E402
from core.drainage import export_geojson  # noqa: E402
from core.elevation import dem  # noqa: E402
from core.hydrology import hydrology  # noqa: E402
from core.score import distance_m  # noqa: E402
from scipy import ndimage  # noqa: E402

ROUTE = PROJECT_DIR / "ui" / "src" / "data" / "route.json"
HOLLOW_MIN_M = 1.0  # display threshold
HOLLOW_MIN_CELLS = 4
COVER_M = 40  # a route point counts as filmed if a dashcam frame is within this distance


def shown_hollows(dep: np.ndarray) -> np.ndarray:
    """Cells that belong to a hollow deep and large enough to be more than DEM noise."""
    labels, _ = ndimage.label(dep > HOLLOW_MIN_M)
    sizes = np.bincount(labels.ravel())
    keep = sizes >= HOLLOW_MIN_CELLS
    keep[0] = False
    return keep[labels]


def hollows_name(city_key: str) -> str:
    return "hollows" if city_key == "delhi" else f"hollows-{city_key}"


def export_hollows(city_key: str = "delhi") -> dict:
    h = hydrology(city_key)
    dep = h.band["depression"]
    ds = h.ds["depression"]
    shown = shown_hollows(dep)
    alpha = np.clip(0.35 + (dep - HOLLOW_MIN_M) / 4, 0.35, 0.85) * shown
    rgba = np.zeros(dep.shape + (4,), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 255, 154, 76  # BGR of #4c9aff
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    cv2.imwrite(str(OUTPUTS_DIR / f"{hollows_name(city_key)}.png"), rgba)
    w, s, e, n = ds.bounds.left, ds.bounds.bottom, ds.bounds.right, ds.bounds.top
    meta = {
        "source": "FABDEM bare-earth DEM (30 m), depressions (filled minus raw) from pysheds",
        "rule": f"deeper than {HOLLOW_MIN_M} m and at least {HOLLOW_MIN_CELLS} cells",
        "coordinates": [[w, n], [e, n], [e, s], [w, s]],
        "cells": int(shown.sum()),
    }
    (OUTPUTS_DIR / f"{hollows_name(city_key)}.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def export_route_profile() -> dict:
    route = json.loads(ROUTE.read_text(encoding="utf-8"))  # [[lng, lat], ...]
    terrain, h = dem("bare"), hydrology()
    shown = shown_hollows(h.band["depression"])
    frames = []
    for path in OUTPUTS_DIR.glob("*-lth/analysis.json"):
        frames += [(f["lat"], f["lng"]) for f in json.loads(path.read_text(encoding="utf-8"))["frames"]]
    pts, d = [], 0.0
    for i, (lng, lat) in enumerate(route):
        if i:
            d += distance_m((route[i - 1][1], route[i - 1][0]), (lat, lng))
        row, col = h.ds["depression"].index(lng, lat)
        hollow = float(h.band["depression"][row, col])
        filmed = any(distance_m((lat, lng), f) <= COVER_M for f in frames)
        pts.append(
            {
                "d": round(d, 1),
                "e": round(terrain.elevation(lat, lng), 2),
                "hollowCm": round(hollow * 100, 1),
                "inHollow": bool(shown[row, col]),
                "filmed": filmed,
            }
        )
    filmed_m = sum(b["d"] - a["d"] for a, b in zip(pts, pts[1:]) if a["filmed"] and b["filmed"])
    profile = {
        "source": "FABDEM bare-earth elevation (30 m) sampled at each route vertex; inHollow uses the map's hollow rule; filmed = dashcam frame within 40 m",
        "hollowRule": f"deeper than {HOLLOW_MIN_M} m and at least {HOLLOW_MIN_CELLS} cells",
        "lengthM": round(d),
        "filmedM": round(filmed_m),
        "points": pts,
    }
    (OUTPUTS_DIR / "route_profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return profile


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="delhi", choices=sorted(CITIES))
    key = parser.parse_args().city
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    m = export_hollows(key)
    print(f"{hollows_name(key)}.png: {m['cells']} cells ({m['rule']})")
    export_geojson(key)
    print(CITIES[key].drains_name)
    if key != "delhi":
        # Reported spots for the map (Delhi's come from validation.json, see run_validate.py).
        ref = PROJECT_DIR / "backend" / "validation" / f"reference_{key}.geo.json"
        if ref.exists():
            (OUTPUTS_DIR / f"reported-{key}.json").write_text(ref.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"reported-{key}.json")
        raise SystemExit
    p = export_route_profile()
    es = [x["e"] for x in p["points"]]
    print(
        f"route_profile.json: {p['lengthM']} m, filmed {p['filmedM']} m, elevation {min(es):.1f}-{max(es):.1f} m, "
        f"{sum(x['inHollow'] for x in p['points'])} of {len(p['points'])} points in a shown hollow"
    )
