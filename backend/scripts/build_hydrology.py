"""Build the water-flow layers (depressions, upstream area, wetness index) for a city on FABDEM.

usage: python scripts/build_hydrology.py [--city delhi|bengaluru]
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cities import CITIES  # noqa: E402
from core.hydrology import build, hydrology  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="delhi", choices=sorted(CITIES))
    key = parser.parse_args().city
    t = time.perf_counter()
    paths = build(CITIES[key])
    print(f"built in {time.perf_counter() - t:.0f}s: {', '.join(p.name for p in paths.values())}")
    h = hydrology(key)
    for name, band in h.band.items():
        v = band[np.isfinite(band)]
        print(f"  {name:<10} p50 {np.percentile(v, 50):.3g}  p90 {np.percentile(v, 90):.3g}  p99 {np.percentile(v, 99):.3g}  max {v.max():.3g}")
