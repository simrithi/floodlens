"""Terrain from 30 m elevation models.

- "surface": Copernicus GLO-30 DSM (AWS Registry of Open Data). Includes buildings and trees.
- "bare":    FABDEM, the same grid with buildings and trees removed (University of Bristol).
             Used by default when the city's FABDEM tile exists (scripts/fetch_fabdem.py).
Tiles are per city (core/cities.py); Delhi's live directly in data/geo/.
"""

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
import requests

from .cities import City, city


def ensure_dem(c: City) -> Path:
    """Download the city's Copernicus DEM tile once (about 40 MB) and return its local path."""
    path = c.geo_dir / f"{c.dem_tile}.tif"
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(c.dem_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(path)
    return path


class Dem:
    def __init__(self, path: Path, kind: str = "surface"):
        self.kind = kind
        self.ds = rasterio.open(path)
        self.band = self.ds.read(1, masked=True)

    def _index(self, lat: float, lng: float) -> tuple[int, int]:
        row, col = self.ds.index(lng, lat)
        if not (0 <= row < self.band.shape[0] and 0 <= col < self.band.shape[1]):
            raise ValueError(f"({lat}, {lng}) is outside DEM tile {self.ds.name}")
        return row, col

    def contains(self, lat: float, lng: float) -> bool:
        try:
            self._index(lat, lng)
            return True
        except ValueError:
            return False

    def elevation(self, lat: float, lng: float) -> float:
        """Ground height in metres above sea level (EGM2008) at a point."""
        row, col = self._index(lat, lng)
        return float(self.band[row, col])

    def relative(self, lat: float, lng: float, radius_m: float = 400) -> float:
        """Point height minus the mean height of the surrounding disc. Negative = local low spot."""
        row, col = self._index(lat, lng)
        res_y = abs(self.ds.transform.e) * 111_320
        res_x = abs(self.ds.transform.a) * 111_320 * math.cos(math.radians(lat))
        ry, rx = max(1, round(radius_m / res_y)), max(1, round(radius_m / res_x))
        r0, c0 = max(0, row - ry), max(0, col - rx)
        window = self.band[r0 : row + ry + 1, c0 : col + rx + 1]
        # Offsets of each window cell from the centre, so the disc stays aligned at tile edges.
        yy = (np.arange(r0, r0 + window.shape[0]) - row)[:, None]
        xx = (np.arange(c0, c0 + window.shape[1]) - col)[None, :]
        disc = ((yy * res_y) ** 2 + (xx * res_x) ** 2) <= radius_m**2
        return float(self.band[row, col] - window[disc].mean())


def default_kind(city_key: str = "delhi") -> str:
    return "bare" if city(city_key).fabdem_path.exists() else "surface"


@lru_cache(maxsize=4)
def dem(kind: str | None = None, city_key: str = "delhi") -> Dem:
    """Cached elevation model. kind: "bare" (FABDEM), "surface" (Copernicus DSM) or None for the best available."""
    c = city(city_key)
    kind = kind or default_kind(city_key)
    if kind == "bare":
        if not c.fabdem_path.exists():
            raise FileNotFoundError(f"{c.fabdem_path} missing; run scripts/fetch_fabdem.py --city {city_key}")
        return Dem(c.fabdem_path, "bare")
    return Dem(ensure_dem(c), "surface")
