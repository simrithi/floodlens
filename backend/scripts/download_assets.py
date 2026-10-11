"""Download every model and dataset the pipeline needs, then load each once to verify it.

usage: python scripts/download_assets.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import models  # noqa: E402
from core.elevation import dem, ensure_dem  # noqa: E402
from core.rainfall import rainfall_stats  # noqa: E402


def step(name, fn):
    t = time.perf_counter()
    result = fn()
    print(f"[ok] {name} ({time.perf_counter() - t:.1f}s)")
    return result


if __name__ == "__main__":
    print(f"device: {models.device()}")
    step("pothole model (YOLOv8m-seg)", models.pothole_model)
    step("road segmentation (SegFormer-B2 Cityscapes)", models.segformer)
    step("depth (Depth Anything V2 Small)", models.depth_model)
    path = step("Copernicus DEM tile", ensure_dem)
    print(f"     {path} ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"     Minto Bridge underpass elevation: {dem().elevation(28.6337, 77.2234):.1f} m")
    stats = step("rainfall history (Open-Meteo ERA5)", rainfall_stats)
    print(f"     wettest hour 2021-2025: {stats['maxHourlyMm']} mm")
