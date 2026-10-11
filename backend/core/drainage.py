"""Drainage network per city: the official storm-water drain map where one is public, else OpenStreetMap.

Bengaluru: KSRSAC's 2022 map of BBMP storm-water drains (primary rajakaluves, secondary, tertiary roadside
drains), published by OpenCity (public domain). It records where drains are and their tier, not their size,
capacity or condition.
Delhi: no drain map is public (the 2025 master plan's GIS model is not released), so OpenStreetMap
waterways: the major open channels, with most roadside drains missing.
"""

import json
import math
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from .cities import City, city
from .config import OUTPUTS_DIR
from .osmtiles import fetch_lines

CLASSES = {"drain", "canal", "river", "stream", "ditch"}
STEP_M = 15  # densify lines so nearest-point distance is accurate to ~8 m


def waterways(c: City) -> list[dict]:
    if c.official_drains:
        lines = json.loads((c.geo_dir / c.official_drains).read_text(encoding="utf-8"))
        return [{"class": ln["type"].lower(), "name": "", "tunnel": False, "coords": ln["coords"]} for ln in lines]
    w, s, e, n = c.bounds
    return fetch_lines("waterway", CLASSES, c.geo_dir / c.waterways_cache, bbox=(s, w, n, e))


class Drainage:
    def __init__(self, c: City):
        self.city = c
        self.lines = waterways(c)
        pts, owner = [], []
        for i, w in enumerate(self.lines):
            for (la1, lo1), (la2, lo2) in zip(w["coords"], w["coords"][1:]):
                d = math.hypot((la2 - la1) * 111_320, (lo2 - lo1) * 111_320 * math.cos(math.radians(la1)))
                k = max(1, int(d // STEP_M))
                for t in np.linspace(0, 1, k, endpoint=False):
                    pts.append((la1 + (la2 - la1) * t, lo1 + (lo2 - lo1) * t))
                    owner.append(i)
            pts.append(w["coords"][-1])
            owner.append(i)
        self.points = np.array(pts)
        self.owner = np.array(owner)
        self._lat0 = math.radians(c.center[0])
        self.tree = cKDTree(self._xy(self.points))

    def _xy(self, latlng: np.ndarray) -> np.ndarray:
        return np.column_stack([latlng[:, 1] * 111_320 * math.cos(self._lat0), latlng[:, 0] * 111_320])

    def nearest(self, lat: float, lng: float) -> dict:
        """Distance (m) to the nearest mapped drain/canal/river and what it is."""
        d, i = self.tree.query(self._xy(np.array([[lat, lng]]))[0])
        w = self.lines[self.owner[i]]
        return {"distanceM": float(d), "class": w["class"], "name": w["name"], "tunnel": w["tunnel"]}

    def capacity_mm_hr(self, distance_m: float) -> float:
        """Rain intensity the drains at a spot are designed to take: the city's documented standard where the
        road is served (an official drain within served_m, or anywhere if the city has no official map), and
        nothing where the official map shows no drain."""
        c = self.city
        if not c.official_drains or distance_m <= c.served_m:
            return c.design_mm_hr
        return 0.0

    def geojson(self, tolerance_deg: float = 0.00003) -> dict:
        """For the map: lines simplified to about 3 m and 5 decimals (about 1 m), so the file stays small.
        Distances (nearest) use the full geometry."""
        from shapely.geometry import LineString

        features = []
        for w in self.lines:
            line = LineString([(lng, lat) for lat, lng in w["coords"]]).simplify(tolerance_deg)
            coords = [[round(x, 5), round(y, 5)] for x, y in line.coords]
            if len(coords) >= 2:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"class": w["class"], "name": w["name"], "tunnel": w["tunnel"]},
                        "geometry": {"type": "LineString", "coordinates": coords},
                    }
                )
        return {"type": "FeatureCollection", "features": features}


@lru_cache(maxsize=2)
def drainage(city_key: str = "delhi") -> Drainage:
    return Drainage(city(city_key))


def export_geojson(city_key: str = "delhi") -> None:
    """Write the city's drains geojson (data/outputs/drains.geojson for Delhi) for the UI map overlay."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUTS_DIR / city(city_key).drains_name).write_text(json.dumps(drainage(city_key).geojson(), separators=(",", ":")), encoding="utf-8")
