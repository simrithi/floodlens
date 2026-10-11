"""Paths, model ids and camera constants shared by every pipeline stage."""

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("FLOODLENS_DATA_DIR", PROJECT_DIR / "data"))
MODELS_DIR = Path(os.environ.get("FLOODLENS_MODELS_DIR", BACKEND_DIR / "models"))
KARTAVIEW_DIR = DATA_DIR / "kartaview"
GEO_DIR = DATA_DIR / "geo"
OUTPUTS_DIR = DATA_DIR / "outputs"

# Hugging Face downloads go next to the code, not into the user profile.
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

POTHOLE_REPO = "keremberke/yolov8m-pothole-segmentation"
SEGFORMER_REPO = "nvidia/segformer-b2-finetuned-cityscapes-1024-1024"
DEPTH_REPO = "depth-anything/Depth-Anything-V2-Small-hf"

# Elevation tiles (Copernicus GLO-30 from the AWS Registry of Open Data; FABDEM bare earth, University of
# Bristol, CC BY-NC-SA 4.0) are per city: see core/cities.py.

# Cityscapes label ids used by SegFormer.
ROAD, SIDEWALK = 0, 1
# Things standing on the road: person, rider, car, truck, bus, train, motorcycle, bicycle.
OBSTACLES = (11, 12, 13, 14, 15, 16, 17, 18)


@dataclass(frozen=True)
class Camera:
    # Default: Xiaomi MI 9 main camera (Delhi sequence). Each sequence's own value from KartaView
    # metadata (frames.json "camera") overrides it, see frames.camera_for().
    hfov_deg: float = 67.935
    # Phone on the dashboard: lens height above the road (metres). Sets the metric scale.
    height_m: float = 1.25
    # Bottom share of the frame showing the car's own dashboard.
    hood_fraction: float = 0.06


CAMERA = Camera()

# Frames wider than this are downscaled before analysis (4K -> 1920x1080).
MAX_WORK_WIDTH = 1920

# Only trust geometry on road between these distances from the camera (metres).
MIN_RANGE_M = 3.5
MAX_RANGE_M = 14.0
