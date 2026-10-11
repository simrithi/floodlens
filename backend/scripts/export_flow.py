"""Export surface-water flow paths around a dashcam survey, for the animated "where the water goes" map layer.

Flow directions (D8) and accumulation are computed on the city's FABDEM bare-earth crop, the same way as
core/hydrology.py, so a path ends where the hydrology layers say water pools. Only paths draining at least
MIN_UPSTREAM_HA are kept (smaller ones are DEM noise at 30 m), clipped to the survey area plus a margin.

Writes data/outputs/<sequence>-<size>/flow.geojson: LineStrings in the downhill direction, with
upstreamHa (land draining through the path's lowest point).

usage: python scripts/export_flow.py --sequence 3827609 [--size lth]
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cities import city_for  # noqa: E402
from core.config import OUTPUTS_DIR  # noqa: E402

MIN_UPSTREAM_HA = 4.0
MARGIN_M = 900


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--size", default="lth")
    args = parser.parse_args()
    out_dir = OUTPUTS_DIR / f"{args.sequence}-{args.size}"
    analysis = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    lats = [f["lat"] for f in analysis["frames"]]
    lngs = [f["lng"] for f in analysis["frames"]]
    c = city_for(lats[0], lngs[0])
    dlat = MARGIN_M / 111_320
    dlng = MARGIN_M / (111_320 * math.cos(math.radians(lats[0])))
    w, s, e, n = min(lngs) - dlng, min(lats) - dlat, max(lngs) + dlng, max(lats) + dlat

    from pysheds.grid import Grid

    if not hasattr(np, "in1d"):
        np.in1d = np.isin  # pysheds 0.5 on NumPy 2.4, see core/hydrology.py
    crop = c.hydro_dir / "dem_crop.tif"
    grid = Grid.from_raster(str(crop))
    dem = grid.read_raster(str(crop))
    flooded = grid.fill_depressions(grid.fill_pits(dem))
    fdir = grid.flowdir(grid.resolve_flats(flooded))
    acc = grid.accumulation(fdir)
    t = grid.affine
    cell_ha = abs(t.a * t.e) * 111_320**2 * math.cos(math.radians(lats[0])) / 1e4
    network = grid.extract_river_network(fdir, acc > MIN_UPSTREAM_HA / cell_ha)

    acc = np.asarray(acc)

    def upstream_ha(lng: float, lat: float) -> float:
        col, row = ~t * (lng, lat)
        return float(acc[min(acc.shape[0] - 1, int(row)), min(acc.shape[1] - 1, int(col))]) * cell_ha

    features = []
    for f in network["features"]:
        # pysheds gives cell corners; move to cell centres so the line runs down the middle of each cell.
        coords = [(x + t.a / 2, y + t.e / 2) for x, y in f["geometry"]["coordinates"]]
        coords = [p for p in coords if w <= p[0] <= e and s <= p[1] <= n]
        if len(coords) < 2:
            continue
        # Downhill order: accumulation grows along the flow. (pysheds does not guarantee the order.)
        ups = [upstream_ha(*p) for p in coords]
        if np.polyfit(np.arange(len(ups)), ups, 1)[0] < 0:
            coords, ups = coords[::-1], ups[::-1]
        up = max(ups)
        features.append(
            {
                "type": "Feature",
                "properties": {"upstreamHa": round(up, 1)},
                "geometry": {"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in coords]},
            }
        )
    geo = {
        "type": "FeatureCollection",
        "source": f"FABDEM bare earth (30 m), D8 flow paths draining at least {MIN_UPSTREAM_HA} ha, pysheds",
        "features": features,
    }
    (out_dir / "flow.geojson").write_text(json.dumps(geo), encoding="utf-8")
    print(f"{len(features)} flow paths -> {out_dir / 'flow.geojson'}")


if __name__ == "__main__":
    main()
