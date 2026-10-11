"""Geocode validation/reference_hotspots.json with OpenStreetMap Nominatim.

Writes validation/reference_hotspots.geo.json. Respects Nominatim's usage policy (1 request/s,
identifying User-Agent). Manual corrections in OVERRIDES win over the geocoder.

usage: python scripts/geocode_hotspots.py
"""

import json
import sys
import time
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parent.parent
SRC = BACKEND / "validation" / "reference_hotspots.json"
OUT = BACKEND / "validation" / "reference_hotspots.geo.json"
DELHI_VIEWBOX = "76.84,28.88,77.35,28.40"  # left, top, right, bottom
HEADERS = {"User-Agent": "FloodLens-hackathon/0.1 (github.com/raghavendrag2002/floodlens)"}

# Hand-checked coordinates where the geocoder picks the wrong feature or a too-large area.
OVERRIDES: dict[str, tuple[float, float, str]] = {
    "R03": (28.6297, 77.2499, "approximate: Ring Road at Indraprastha Estate, WHO SEARO office"),
    "R09": (28.5737, 77.2276, "approximate: Defence Colony flyover, Lala Lajpat Rai Marg"),
    "R17": (28.5492, 77.2519, "approximate: Nehru Place (Nominatim returned Motilal Nehru Place)"),
    "R18": (28.5553, 77.2425, "approximate: Kailash Colony metro, Lala Lajpat Rai Marg"),
    "R22": (28.5843, 77.2380, "approximate: Jangpura metro"),
    "R29": (28.6235, 77.2505, "approximate: Ring Road at IP flyover (Nominatim returned Nirman Vihar)"),
    "R31": (28.6110, 77.2470, "approximate: Bhairon Marg near Ring Road"),
}


def geocode(query: str) -> dict | None:
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "jsonv2", "limit": 1, "viewbox": DELHI_VIEWBOX, "bounded": 1},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    hits = r.json()
    return hits[0] if hits else None


def main() -> None:
    ref = json.loads(SRC.read_text(encoding="utf-8"))
    out = []
    for h in ref["hotspots"]:
        if h["id"] in OVERRIDES:
            lat, lng, note = OVERRIDES[h["id"]]
            out.append({**h, "lat": lat, "lng": lng, "geocoded": f"manual: {note}"})
            continue
        hit = geocode(h["query"])
        time.sleep(1.1)
        if not hit:
            print(f"[miss] {h['id']} {h['query']}", file=sys.stderr)
            out.append({**h, "lat": None, "lng": None, "geocoded": "not found"})
            continue
        out.append({**h, "lat": round(float(hit["lat"]), 6), "lng": round(float(hit["lon"]), 6), "geocoded": hit["display_name"][:120]})
        print(f"{h['id']} {h['name']:<40} {float(hit['lat']):.5f},{float(hit['lon']):.5f}  {hit['display_name'][:70]}")
    OUT.write_text(json.dumps({**ref, "hotspots": out}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
