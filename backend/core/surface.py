"""Road surface features: depressions where water collects, and the road-to-kerb height step."""

from dataclasses import dataclass

import cv2
import numpy as np

from .config import OBSTACLES, ROAD, SIDEWALK
from .geometry import GroundModel, range_mask


@dataclass
class Dip:
    depth_cm: float  # 90th percentile depth below the road plane
    area_m2: float
    distance_m: float  # forward distance from the camera to the dip centre
    centroid: tuple[int, int]  # pixel (x, y)
    polygon: np.ndarray  # (N, 2) int32 outline


@dataclass
class Kerb:
    drop_cm: float  # how far the road surface sits below the footpath edge
    side: str  # "left" or "right" of the camera
    points: np.ndarray  # (N, 2) int32 pixels along the road/footpath boundary
    samples: int


def clear_road(labels: np.ndarray, image: np.ndarray | None = None) -> np.ndarray:
    """Road pixels we trust for height: away from road edges, vehicles, people and their shadows.

    Depth models blend an object into the road where it touches it, and read a dark shadow as a
    hollow. So we drop a band around obstacles that reaches further below them (where shadows fall),
    trim the road boundary, and drop pixels much darker than the typical road surface.
    """
    h, w = labels.shape
    side, below = max(9, w // 50), max(15, h // 12)
    obstacles = np.isin(labels, OBSTACLES).astype(np.uint8)
    kernel = np.zeros((2 * below + 1, 2 * side + 1), np.uint8)
    kernel[below // 3 :, :] = 1  # mostly downward: the shadow and contact zone under an object
    near_obstacle = cv2.dilate(obstacles, kernel).astype(bool)
    edge = max(7, w // 90)
    road = cv2.erode((labels == ROAD).astype(np.uint8), np.ones((edge, edge), np.uint8)).astype(bool)
    keep = road & ~near_obstacle
    if image is not None and keep.any():
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32)
        keep &= gray > 0.62 * np.median(gray[keep])
    return keep


def find_dips(
    height: np.ndarray,
    labels: np.ndarray,
    model: GroundModel,
    image: np.ndarray | None = None,
    min_depth_m: float = 0.03,
    min_area_m2: float = 0.4,
    max_dips: int = 6,
) -> list[Dip]:
    """Connected road regions that sit measurably below the fitted road plane."""
    road = clear_road(labels, image) & range_mask(labels.shape, model)
    if road.sum() < 500:
        return []
    filled = np.where(road & np.isfinite(height), height, 0).astype(np.float32)
    smooth = cv2.GaussianBlur(filled, (0, 0), 4)
    weight = cv2.GaussianBlur(road.astype(np.float32), (0, 0), 4)
    smooth = np.divide(smooth, weight, out=np.zeros_like(smooth), where=weight > 0.2)

    # Ignore depressions shallower than the fit's own noise level. Height error grows with
    # distance (delta is proportional to Z for a fixed disparity error), so the bar rises with range.
    noise = 1.4826 * np.nanmedian(np.abs(smooth[road] - np.nanmedian(smooth[road])))
    z = model.distance(np.arange(labels.shape[0]))[:, None]
    threshold = np.maximum(max(min_depth_m, 2.5 * noise), 0.004 * z)
    candidate = (road & (smooth > threshold)).astype(np.uint8)
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

    n, comp, stats, centroids = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    area_per_px = model.pixel_area_m2(np.arange(labels.shape[0]))
    dips: list[Dip] = []
    for i in range(1, n):
        region = comp == i
        ys, _ = np.nonzero(region)
        area = float(np.nansum(area_per_px[ys]))
        if area < min_area_m2:
            continue
        cx, cy = centroids[i]
        contours, _ = cv2.findContours(region.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        poly = max(contours, key=cv2.contourArea).reshape(-1, 2)
        dips.append(
            Dip(
                depth_cm=float(np.percentile(smooth[region], 90) * 100),
                area_m2=area,
                distance_m=float(model.distance(cy)),
                centroid=(int(cx), int(cy)),
                polygon=poly.astype(np.int32),
            )
        )
    dips.sort(key=lambda d: d.depth_cm * d.area_m2, reverse=True)
    return dips[:max_dips]


def measure_kerb(height: np.ndarray, labels: np.ndarray, model: GroundModel) -> Kerb | None:
    """Height of the footpath edge above the adjacent road, from pixels either side of the boundary."""
    in_range = range_mask(labels.shape, model)
    road = (labels == ROAD) & in_range
    side = (labels == SIDEWALK) & in_range
    if side.sum() < 400 or road.sum() < 400:
        return None
    k = np.ones((9, 9), np.uint8)
    side_edge = side & cv2.dilate(road.astype(np.uint8), k).astype(bool)
    road_edge = road & cv2.dilate(side.astype(np.uint8), k).astype(bool)
    top = height[side_edge]
    bottom = height[road_edge]
    top, bottom = top[np.isfinite(top)], bottom[np.isfinite(bottom)]
    if top.size < 80 or bottom.size < 80:
        return None
    # height is "metres below the road plane", so the footpath top is negative.
    drop = float(np.median(bottom) - np.median(top))
    if not 0.02 <= drop <= 0.45:
        return None
    ys, xs = np.nonzero(road_edge)
    order = np.argsort(ys)
    pts = np.column_stack([xs[order], ys[order]])[:: max(1, len(order) // 60)]
    return Kerb(
        drop_cm=drop * 100,
        side="left" if xs.mean() < model.cx else "right",
        points=pts.astype(np.int32),
        samples=int(top.size + bottom.size),
    )
