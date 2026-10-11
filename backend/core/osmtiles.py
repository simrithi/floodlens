"""OpenStreetMap lines (roads, waterways) for a city, read from CARTO vector tiles.

These are the same tiles the UI map draws. The Overpass API was tried first but its public instances
returned 504/500 for every query during development.
"""

import json
import math
from pathlib import Path

import requests

TILE_URL = "https://tiles-a.basemaps.cartocdn.com/vectortiles/carto.streets/v1/{z}/{x}/{y}.mvt"
DELHI_BBOX = (28.42, 76.90, 28.82, 77.32)  # south, west, north, east


def fetch_lines(layer: str, classes: set[str], cache: Path, zoom: int = 13, bbox=DELHI_BBOX) -> list[dict]:
    """Lines of `layer` whose `class` is in `classes`: [{"class", "name", "tunnel", "coords": [(lat, lng), ...]}]."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import mapbox_vector_tile

    s, w, n, e = bbox
    size = 2**zoom

    def tile_xy(lat: float, lng: float) -> tuple[int, int]:
        x = int((lng + 180) / 360 * size)
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size)
        return x, y

    def to_latlng(tx: int, ty: int, px: float, py: float, extent: int) -> tuple[float, float]:
        fx, fy = (tx + px / extent) / size, (ty + py / extent) / size
        return round(math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * fy)))), 6), round(fx * 360 - 180, 6)

    x0, y0 = tile_xy(n, w)
    x1, y1 = tile_xy(s, e)
    out: list[dict] = []
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            r = requests.get(TILE_URL.format(z=zoom, x=tx, y=ty), timeout=30, headers={"User-Agent": "FloodLens-hackathon/0.1"})
            r.raise_for_status()
            lyr = mapbox_vector_tile.decode(r.content, default_options={"y_coord_down": True}).get(layer)
            if not lyr:
                continue
            ext = lyr["extent"]
            for f in lyr["features"]:
                props = f["properties"]
                if props.get("class") not in classes:
                    continue
                g = f["geometry"]
                lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
                for line in lines:
                    # Drop the tile buffer so features are not counted twice at tile edges.
                    pts = [to_latlng(tx, ty, px, py, ext) for px, py in line if 0 <= px <= ext and 0 <= py <= ext]
                    if len(pts) >= 2:
                        out.append(
                            {
                                "class": props["class"],
                                "name": props.get("name_en") or props.get("name") or "",
                                "tunnel": props.get("brunnel") == "tunnel",
                                "coords": pts,
                            }
                        )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out
