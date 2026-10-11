"""Terrain from the Copernicus GLO-30 DEM (30 m grid, AWS Registry of Open Data)."""

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
import requests

from .config import DEM_TILE, DEM_URL, GEO_DIR


def ensure_dem() -> Path:
    """Download the Delhi DEM tile once (about 42 MB) and return its local path."""
    path = GEO_DIR / f"{DEM_TILE}.tif"
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with requests.get(DEM_URL, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(path)
    return path


class Dem:
    def __init__(self, path: Path | None = None):
        self.ds = rasterio.open(path or ensure_dem())
        self.band = self.ds.read(1, masked=True)

    def elevation(self, lat: float, lng: float) -> float:
        """Ground height in metres above sea level (EGM2008) at a point."""
        row, col = self.ds.index(lng, lat)
        return float(self.band[row, col])

    def relative(self, lat: float, lng: float, radius_m: float = 400) -> float:
        """Point height minus the mean height of the surrounding disc. Negative = local low spot."""
        row, col = self.ds.index(lng, lat)
        res_y = abs(self.ds.transform.e) * 111_320
        res_x = abs(self.ds.transform.a) * 111_320 * math.cos(math.radians(lat))
        ry, rx = max(1, round(radius_m / res_y)), max(1, round(radius_m / res_x))
        window = self.band[max(0, row - ry) : row + ry + 1, max(0, col - rx) : col + rx + 1]
        yy, xx = np.ogrid[-ry : ry + 1, -rx : rx + 1]
        disc = ((yy * res_y) ** 2 + (xx * res_x) ** 2) <= radius_m**2
        disc = disc[: window.shape[0], : window.shape[1]]
        return float(self.band[row, col] - window[disc].mean())


@lru_cache(maxsize=1)
def dem() -> Dem:
    return Dem()
