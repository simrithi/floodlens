"""Download the on-route frames of a KartaView sequence (two sizes) plus GPS metadata.

Reproduces data/kartaview/<sequence>/ exactly. Files that already exist are skipped.

usage: python scripts/fetch_kartaview.py [--sequence 4020141]
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import KARTAVIEW_DIR  # noqa: E402

API = "https://api.openstreetcam.org/2.0/photo/"
# sequenceIndex ranges of sequence 4020141 that lie on the demo route (found by matching GPS to the route).
SEGMENTS = [
    {"name": "ito", "from": 433, "to": 570, "label": "ITO crossing approach"},
    {"name": "minto", "from": 1375, "to": 1443, "label": "Minto Bridge underpass"},
]
SIZES = {"lth": "fileurlLTh", "full": "fileurlProc"}

ATTRIBUTION = """# Source and licence

Imagery: KartaView sequence {seq}, recorded 2021-12-21 on a Xiaomi MI 9 (video mode, dashboard mount),
uploaded by KartaView user #13451. https://kartaview.org/details/{seq}

Licence: Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)
https://creativecommons.org/licenses/by-sa/4.0/

Faces and number plates were blurred by KartaView before publication.
Any derived images we publish (overlays, crops) must keep this attribution and the CC BY-SA 4.0 licence.

- lth/  KartaView "large thumbnail" size
- full/ original processed frames, 3840x2160
- frames.json  GPS, heading and timestamp per frame
"""


def list_photos(sequence_id: int) -> list[dict]:
    photos, page = [], 1
    while True:
        r = requests.get(API, params={"sequenceId": sequence_id, "itemsPerPage": 150, "page": page}, timeout=60)
        r.raise_for_status()
        batch = r.json()["result"]["data"]
        photos += batch
        if len(batch) < 150:
            return sorted(photos, key=lambda p: int(p["sequenceIndex"]))
        page += 1


def segment_of(index: int) -> str | None:
    return next((s["name"] for s in SEGMENTS if s["from"] <= index <= s["to"]), None)


def download(url: str, path: Path) -> int:
    if path.exists() and path.stat().st_size > 0:
        return 0
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/jpeg"):
        raise ValueError(f"unexpected content type for {url}")
    path.write_bytes(r.content)
    return len(r.content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence", type=int, default=4020141)
    args = parser.parse_args()
    out = KARTAVIEW_DIR / str(args.sequence)

    picked = [p for p in list_photos(args.sequence) if segment_of(int(p["sequenceIndex"]))]
    jobs = []
    for size, key in SIZES.items():
        (out / size).mkdir(parents=True, exist_ok=True)
        jobs += [(p[key], out / size / f"{int(p['sequenceIndex']):04d}.jpg") for p in picked]
    with ThreadPoolExecutor(6) as pool:
        downloaded = sum(pool.map(lambda job: download(*job), jobs))

    frames = [
        {
            "index": int(p["sequenceIndex"]),
            "id": int(p["id"]),
            "segment": segment_of(int(p["sequenceIndex"])),
            "lat": float(p["lat"]),
            "lng": float(p["lng"]),
            "matchLat": float(p["matchLat"]) if p.get("matchLat") else None,
            "matchLng": float(p["matchLng"]) if p.get("matchLng") else None,
            "heading": float(p["heading"]) if p.get("heading") else None,
            "gpsAccuracy": float(p["gpsAccuracy"]) if p.get("gpsAccuracy") else None,
            "shotDate": p["shotDate"],
            "width": int(p["width"]),
            "height": int(p["height"]),
            "file": f"{int(p['sequenceIndex']):04d}.jpg",
        }
        for p in picked
    ]
    meta = {"sequenceId": args.sequence, "segments": SEGMENTS, "frames": frames}
    (out / "frames.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out / "ATTRIBUTION.md").write_text(ATTRIBUTION.format(seq=args.sequence), encoding="utf-8")
    print(f"{len(picked)} frames, {len(jobs)} files, {downloaded / 1e6:.1f} MB newly downloaded -> {out}")


if __name__ == "__main__":
    main()
