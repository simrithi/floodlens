"""Surface water flow on the bare-earth DEM (FABDEM): where water pools and how much land drains to a spot.

Built once per city (scripts/build_hydrology.py --city) and saved as GeoTIFFs in <city geo dir>/hydro/:

    depression.tif   depth (m) of the hollow a cell sits in: filled DEM minus DEM. Water pools here.
    upstream.tif     area (m2) of land whose runoff flows through the cell (D8 flow accumulation).
    twi.tif          topographic wetness index ln(a / tan(slope)); higher = wetter.

The DEM grid is 30 m, so a road underpass (10-15 m wide) is below its resolution. These layers describe
the neighbourhood-scale terrain the road sits in; the dashcam supplies the street-scale shape.
"""

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from .cities import City, city

LAYERS = ("depression", "upstream", "twi")


def build(c: City) -> dict[str, Path]:
    """Compute and save the hydrology rasters for the city's bounds. Takes about a minute."""
    from pysheds.grid import Grid

    # pysheds 0.5 still calls np.in1d, removed in NumPy 2.4; np.isin is its documented replacement.
    if not hasattr(np, "in1d"):
        np.in1d = np.isin

    hydro_dir = c.hydro_dir
    hydro_dir.mkdir(parents=True, exist_ok=True)
    crop = hydro_dir / "dem_crop.tif"
    with rasterio.open(c.fabdem_path) as src:
        window = from_bounds(*c.bounds, transform=src.transform).round_offsets().round_lengths()
        data = src.read(1, window=window).astype(np.float32)
        profile = src.profile | {
            "height": data.shape[0],
            "width": data.shape[1],
            "transform": src.window_transform(window),
            "dtype": "float32",
            "nodata": -9999.0,
            "compress": "deflate",
        }
    with rasterio.open(crop, "w", **profile) as dst:
        dst.write(data, 1)

    grid = Grid.from_raster(str(crop))
    dem = grid.read_raster(str(crop))
    flooded = grid.fill_depressions(grid.fill_pits(dem))
    fdir = grid.flowdir(grid.resolve_flats(flooded))
    acc = np.asarray(grid.accumulation(fdir), dtype=np.float64)

    lat = c.center[0]
    dy = abs(profile["transform"].e) * 111_320
    dx = abs(profile["transform"].a) * 111_320 * math.cos(math.radians(lat))
    cell_area = dx * dy

    depression = (np.asarray(flooded) - np.asarray(dem)).astype(np.float32)
    upstream = (acc * cell_area).astype(np.float32)
    gy, gx = np.gradient(np.asarray(dem, dtype=np.float64), dy, dx)
    tan_slope = np.maximum(np.hypot(gx, gy), 1e-3)
    twi = np.log((acc * cell_area / math.sqrt(cell_area)) / tan_slope).astype(np.float32)

    out = {}
    for name, arr in (("depression", depression), ("upstream", upstream), ("twi", twi)):
        path = hydro_dir / f"{name}.tif"
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr, 1)
        out[name] = path
    return out


class Hydrology:
    def __init__(self, c: City):
        d = c.hydro_dir
        missing = [n for n in LAYERS if not (d / f"{n}.tif").exists()]
        if missing:
            raise FileNotFoundError(f"hydrology layers missing ({', '.join(missing)}); run scripts/build_hydrology.py --city {c.key}")
        self.ds = {n: rasterio.open(d / f"{n}.tif") for n in LAYERS}
        self.band = {n: ds.read(1) for n, ds in self.ds.items()}
        t = self.ds["depression"].transform
        self.res_y = abs(t.e) * 111_320
        self.res_x = abs(t.a) * 111_320 * math.cos(math.radians(c.center[0]))

    def contains(self, lat: float, lng: float) -> bool:
        row, col = self.ds["depression"].index(lng, lat)
        h, w = self.band["depression"].shape
        return 0 <= row < h and 0 <= col < w

    def sample(self, lat: float, lng: float, radius_m: float = 60) -> dict[str, float]:
        """Maximum of each layer within radius_m (flow lines are one cell wide, positions are approximate),
        plus depressionAreaM2: footprint of hollow cells (> 5 cm deep) inside the same disc."""
        if not self.contains(lat, lng):
            raise ValueError(f"({lat}, {lng}) is outside the hydrology rasters; check the city bounds in core/cities.py")
        row, col = self.ds["depression"].index(lng, lat)
        ry, rx = max(1, round(radius_m / self.res_y)), max(1, round(radius_m / self.res_x))
        out = {}
        for name, band in self.band.items():
            r0, c0 = max(0, row - ry), max(0, col - rx)
            win = band[r0 : row + ry + 1, c0 : col + rx + 1]
            yy = (np.arange(r0, r0 + win.shape[0]) - row)[:, None]
            xx = (np.arange(c0, c0 + win.shape[1]) - col)[None, :]
            disc = ((yy * self.res_y) ** 2 + (xx * self.res_x) ** 2) <= radius_m**2
            out[name] = float(win[disc].max())
            if name == "depression":
                out["depressionAreaM2"] = float((win[disc] > 0.05).sum() * self.res_x * self.res_y)
        return out


@lru_cache(maxsize=2)
def hydrology(city_key: str = "delhi") -> Hydrology:
    return Hydrology(city(city_key))
