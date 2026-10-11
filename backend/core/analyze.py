"""Per-frame analysis: run every perception stage on one frame and geolocate the findings."""

from dataclasses import dataclass, field

import numpy as np

from .config import CAMERA, ROAD, Camera
from .depth import relative_disparity
from .detect import Pothole, detect_potholes
from .frames import Frame
from .geometry import GroundModel, fit_ground, offset_latlng, range_mask, surface_height
from .segment import clean_labels, segment
from .surface import Dip, Kerb, SurfaceFit, clear_road, find_dips, fit_surface, measure_kerbs, residual_height

MIN_POTHOLE_DEPTH_CM = 1.5


@dataclass
class FrameAnalysis:
    frame: Frame
    shape: tuple[int, int]
    road_fraction: float
    ground: GroundModel | None
    potholes: list[Pothole] = field(default_factory=list)
    pothole_depth_cm: list[float] = field(default_factory=list)
    dips: list[Dip] = field(default_factory=list)
    kerbs: list[Kerb] = field(default_factory=list)
    surface: SurfaceFit | None = None
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


def analyze_frame(frame: Frame, image: np.ndarray, pothole_confidence: float = 0.35, camera: Camera = CAMERA) -> FrameAnalysis:
    disparity = relative_disparity(image)
    h = image.shape[0]
    hood = int(h * (1 - camera.hood_fraction)) if camera.hood_fraction > CAMERA.hood_fraction else None
    labels = clean_labels(segment(image), disparity, hood)
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

    ground = fit_ground(disparity, road, camera)
    result.ground = ground
    if ground is None:
        return result

    height = surface_height(disparity, ground)
    result.height = height
    result.kerbs = measure_kerbs(height, labels, ground)
    # Dips are measured against the road's own curved shape (camber, grade change), not a flat plane.
    surface = fit_surface(height, clear_road(labels, image) & range_mask(labels.shape, ground), ground)
    result.surface = surface
    if surface is None:
        return result
    residual = residual_height(height, surface, ground)
    result.dips = find_dips(residual, labels, ground, image)
    for p in result.potholes:
        vals = residual[p.mask & np.isfinite(residual)]
        result.pothole_depth_cm.append(float(np.percentile(vals, 90) * 100) if vals.size else 0.0)
    # A pothole is a hole: keep detections only where the road surface is measurably lower. Rubble,
    # patches and debris at the roadside look similar to the detector but hold no water.
    kept = [(p, d) for p, d in zip(result.potholes, result.pothole_depth_cm) if d >= MIN_POTHOLE_DEPTH_CM]
    result.potholes = [p for p, _ in kept]
    result.pothole_depth_cm = [d for _, d in kept]
    return result
