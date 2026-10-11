"""Loading dashcam frames and their GPS metadata (KartaView download layout)."""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import CAMERA, KARTAVIEW_DIR, MAX_WORK_WIDTH, Camera


@dataclass(frozen=True)
class Frame:
    index: int
    id: int
    segment: str
    lat: float
    lng: float
    heading: float | None
    shot_date: str
    file: str


def sequence_dir(sequence_id: int) -> Path:
    return KARTAVIEW_DIR / str(sequence_id)


def load_frames(sequence_id: int, segments: list[str] | None = None) -> tuple[dict, list[Frame]]:
    """Read frames.json written by the downloader. Returns (raw metadata, frames in capture order)."""
    meta = json.loads((sequence_dir(sequence_id) / "frames.json").read_text(encoding="utf-8"))
    frames = [
        Frame(
            index=f["index"],
            id=f["id"],
            segment=f["segment"],
            lat=f["lat"],
            lng=f["lng"],
            heading=f["heading"],
            shot_date=f["shotDate"],
            file=f["file"],
        )
        for f in meta["frames"]
        if segments is None or f["segment"] in segments
    ]
    frames.sort(key=lambda f: f.index)
    return meta, frames


def camera_for(meta: dict) -> Camera:
    """The sequence's camera: its horizontal field of view from KartaView metadata, else the default."""
    hfov = (meta.get("camera") or {}).get("hfovDeg")
    return Camera(hfov_deg=float(hfov), height_m=CAMERA.height_m, hood_fraction=CAMERA.hood_fraction) if hfov else CAMERA


def load_image(path: Path, max_width: int = MAX_WORK_WIDTH) -> np.ndarray:
    """Read an image as RGB uint8, downscaled so its width is at most max_width."""
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(path)
    h, w = bgr.shape[:2]
    if w > max_width:
        scale = max_width / w
        bgr = cv2.resize(bgr, (max_width, round(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
