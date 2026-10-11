"""Per-frame analysis: run every perception stage on one frame and geolocate the findings."""

from dataclasses import dataclass, field

import numpy as np

from .config import ROAD
from .depth import relative_disparity
from .detect import Pothole, detect_potholes
from .frames import Frame
from .geometry import GroundModel, fit_ground, offset_latlng, surface_height
from .segment import segment
from .surface import Dip, Kerb, clear_road, find_dips, measure_kerb


@dataclass
class FrameAnalysis:
    frame: Frame
    shape: tuple[int, int]
    road_fraction: float
    ground: GroundModel | None
    potholes: list[Pothole] = field(default_factory=list)
    pothole_depth_cm: list[float] = field(default_factory=list)
    dips: list[Dip] = field(default_factory=list)
    kerb: Kerb | None = None
    labels: np.ndarray | None = None
    disparity: np.ndarray | None = None
    height: np.ndarray | None = None

    def locate(self, x: float, y: float) -> tuple[float, float] | None:
        """Pixel -> (lat, lng) on the road, using the frame GPS and heading."""
        if self.ground is None or self.frame.heading is None:
            return None
        forward, right = self.ground.to_ground(x, y)
        if not np.isfinite(forward):
            return None
        return offset_latlng(self.frame.lat, self.frame.lng, self.frame.heading, forward, right)


def analyze_frame(frame: Frame, image: np.ndarray, pothole_confidence: float = 0.35) -> FrameAnalysis:
    labels = segment(image)
    disparity = relative_disparity(image)
    road = labels == ROAD
    result = FrameAnalysis(frame=frame, shape=image.shape[:2], road_fraction=float(road.mean()), ground=None)
    result.labels, result.disparity = labels, disparity
    # The detector was trained on close-up road photos and also fires on trees, signboards and the
    # dark gap under vehicles, so keep only detections lying mostly on open road. (No brightness
    # filter here: a real pothole is often darker than the road around it.)
    open_road = clear_road(labels)
    result.potholes = [
        p for p in detect_potholes(image, pothole_confidence) if open_road[p.mask].mean() >= 0.5
    ]

    ground = fit_ground(disparity, road)
    result.ground = ground
    if ground is None:
        return result

    height = surface_height(disparity, ground)
    result.height = height
    result.dips = find_dips(height, labels, ground, image)
    result.kerb = measure_kerb(height, labels, ground)
    for p in result.potholes:
        vals = height[p.mask & np.isfinite(height)]
        result.pothole_depth_cm.append(float(np.percentile(vals, 90) * 100) if vals.size else 0.0)
    return result
