"""Road surface features: the road's designed shape, local dips that hold water, and the kerb line.

Roads are not flat. They are built with camber (higher in the middle so water runs to the gutters)
and change grade along their length. A flat-plane reference therefore flags both road edges as "dips".
So we work in two steps:

1. geometry.surface_height(): height of every pixel relative to a first flat-plane fit (metres).
2. fit_surface(): a smooth curved surface in ground coordinates (X lateral, Z forward, metres)
       h(X, Z) = c0 + c1 X + c2 X^2 + c3 Z + c4 Z^2 + c5 X Z
   c1 = cross slope, c2 = camber, c3 = grade, c4 = vertical curvature, c5 = twist. A dip is a patch
   that sits below *this* surface, i.e. a deviation from the road's designed shape.

Dips are only searched at least EDGE_BAND_M away from the road boundary (kerb, footpath, verge): the
depth model blurs the vertical kerb face into the road there, and the gutter is the designed low line.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from .config import OBSTACLES, ROAD, SIDEWALK
from .segment import EGO
from .geometry import GroundModel, range_mask

EDGE_BAND_M = 1.0
# Deepest believable dip. Potholes and sunken patches are rarely deeper than ~25 cm; a single camera that
# reports more within 14 m has misread the depth (glare, the bright end of a tunnel).
MAX_DIP_M = 0.40
MIN_KERB_RANGE_M = 3.5
KERB_MAX_RANGE_M = 25.0  # position of the edge line stays usable further out than heights do
# Cityscapes classes that can lie beyond the carriageway edge.
EDGE_CLASSES = (1, 2, 3, 4, 8, 9)  # sidewalk, building, wall, fence, vegetation, terrain
EDGE_NAMES = {1: "footpath", 2: "building", 3: "wall", 4: "fence", 8: "vegetation", 9: "verge"}


@dataclass
class Dip:
    depth_cm: float  # 90th percentile depth below the fitted road surface
    area_m2: float
    distance_m: float  # forward distance from the camera to the dip centre
    centroid: tuple[int, int]  # pixel (x, y)
    polygon: np.ndarray  # (N, 2) int32 outline


@dataclass
class Kerb:
    drop_cm: float | None  # raw single-camera step estimate next to a footpath; reads low, not shown
    side: str  # "left" or "right" of the camera
    points: np.ndarray  # (N, 2) int32 pixels along the carriageway edge, one per row
    samples: int
    beyond: str = "edge"  # what lies beyond the edge: footpath, wall, vegetation, ...
    ground: np.ndarray | None = None  # (N, 2) forward Z, right X in metres from the camera


@dataclass
class SurfaceFit:
    coef: np.ndarray  # c0..c5 for [1, X, X^2, Z, Z^2, X*Z], metres below the flat plane
    camber_cm: float  # how much lower the surface is 3.5 m to the side of its crown
    cross_slope_pct: float
    grade_change: float  # c4, 1/m: vertical curvature of the road ahead relative to the camera
    rmse_cm: float
    samples: int

    def evaluate(self, X: np.ndarray, Z: np.ndarray) -> np.ndarray:
        c = self.coef
        return c[0] + c[1] * X + c[2] * X**2 + c[3] * Z + c[4] * Z**2 + c[5] * X * Z


def ground_coords(shape: tuple[int, int], model: GroundModel) -> tuple[np.ndarray, np.ndarray]:
    """Lateral X and forward Z (metres) of every pixel on the road plane. Inf above the horizon."""
    h, w = shape
    z = model.distance(np.arange(h)).astype(np.float64)[:, None]
    with np.errstate(invalid="ignore"):  # rows above the horizon have infinite distance
        x = (np.arange(w, dtype=np.float64)[None, :] - model.cx) * z / model.fx
    return np.broadcast_to(x, shape), np.broadcast_to(z, shape)


def clear_road(labels: np.ndarray, image: np.ndarray | None = None) -> np.ndarray:
    """Road pixels we trust for height: away from vehicles, people and their shadows.

    Depth models blend an object into the road where it touches it, and read a dark shadow as a
    hollow. So we drop a band around obstacles that reaches further below them (where shadows fall),
    trim the road boundary slightly, and drop pixels much darker than the typical road surface.
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


def away_from_edge(labels: np.ndarray, model: GroundModel, band_m: float = EDGE_BAND_M) -> np.ndarray:
    """Road pixels at least band_m (on the ground) from the road boundary. Vehicles and our own bonnet
    (EGO) do not count as boundary: the road continues under them."""
    road_or_vehicle = (labels == ROAD) | np.isin(labels, OBSTACLES) | (labels == EGO)
    dist_px = cv2.distanceTransform(road_or_vehicle.astype(np.uint8), cv2.DIST_L2, 5)
    metres_per_px = (model.distance(np.arange(labels.shape[0])) / model.fx)[:, None]
    with np.errstate(invalid="ignore"):  # rows above the horizon have infinite distance
        return (labels == ROAD) & (dist_px * metres_per_px >= band_m)


def fit_surface(height: np.ndarray, mask: np.ndarray, model: GroundModel, seed: int = 0) -> SurfaceFit | None:
    """Robust curved-surface fit of road height in ground coordinates."""
    X, Z = ground_coords(height.shape, model)
    ok = mask & np.isfinite(height) & np.isfinite(Z)
    ys, xs = np.nonzero(ok)
    if ys.size < 1500:
        return None
    if ys.size > 25_000:
        pick = np.random.default_rng(seed).choice(ys.size, 25_000, replace=False)
        ys, xs = ys[pick], xs[pick]
    x, z, hgt = X[ys, xs], Z[ys, xs], height[ys, xs].astype(np.float64)
    A = np.column_stack([np.ones_like(x), x, x**2, z, z**2, x * z])
    keep = np.ones(x.size, dtype=bool)
    for _ in range(4):
        coef, *_ = np.linalg.lstsq(A[keep], hgt[keep], rcond=None)
        resid = hgt - A @ coef
        mad = np.median(np.abs(resid[keep] - np.median(resid[keep]))) + 1e-6
        keep = np.abs(resid) < 3.0 * 1.4826 * mad
    return SurfaceFit(
        coef=coef,
        camber_cm=float(coef[2] * 3.5**2 * 100),
        cross_slope_pct=float(coef[1] * 100),
        grade_change=float(coef[4]),
        rmse_cm=float(np.sqrt(np.mean(resid[keep] ** 2)) * 100),
        samples=int(keep.sum()),
    )


def residual_height(height: np.ndarray, fit: SurfaceFit, model: GroundModel) -> np.ndarray:
    """Metres below the fitted road surface (> 0: lower than the road's designed shape)."""
    X, Z = ground_coords(height.shape, model)
    with np.errstate(invalid="ignore"):
        return (height - fit.evaluate(X, Z)).astype(np.float32)


def find_dips(
    residual: np.ndarray,
    labels: np.ndarray,
    model: GroundModel,
    image: np.ndarray | None = None,
    min_depth_m: float = 0.03,
    min_area_m2: float = 0.4,
    max_dips: int = 6,
    max_depth_m: float = MAX_DIP_M,
) -> list[Dip]:
    """Connected road patches that sit measurably below the fitted road surface, away from its edges."""
    road = clear_road(labels, image) & away_from_edge(labels, model) & range_mask(labels.shape, model)
    if road.sum() < 500:
        return []
    filled = np.where(road & np.isfinite(residual), residual, 0).astype(np.float32)
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
        depth = float(np.percentile(smooth[region], 90))
        if depth > max_depth_m:
            continue  # a depth misread (glare, a bright tunnel exit), not a dip a road could hold
        dips.append(
            Dip(
                depth_cm=depth * 100,
                area_m2=area,
                distance_m=float(model.distance(cy)),
                centroid=(int(cx), int(cy)),
                polygon=poly.astype(np.int32),
            )
        )
    dips.sort(key=lambda d: d.depth_cm * d.area_m2, reverse=True)
    return dips[:max_dips]


def _boundary_line(road_edge: np.ndarray, left: bool, step: int) -> np.ndarray:
    """One boundary point per image row on one side: the outermost road-edge pixel."""
    pts = []
    for y in range(0, road_edge.shape[0], step):
        xs = np.flatnonzero(road_edge[y])
        if xs.size:
            pts.append((int(xs.min() if left else xs.max()), y))
    return np.array(pts, dtype=np.int32).reshape(-1, 2)


def _runs_along_road(points: np.ndarray, model: GroundModel) -> bool:
    """A kerb runs along the road: it spans >= 3 m ahead, drifts sideways slowly and is nearly straight.
    Rejects boundaries of patches that cut across the carriageway (pedestrians, islands)."""
    gp = np.array([model.to_ground(float(x), float(y)) for x, y in points])  # (forward Z, right X)
    gp = gp[np.isfinite(gp).all(axis=1)]
    if len(gp) < 5:
        return False
    z, x = gp[:, 0], gp[:, 1]
    if z.max() - z.min() < 3.0:
        return False
    slope, intercept = np.polyfit(z, x, 1)
    straightness = np.std(x - (slope * z + intercept))
    return abs(slope) <= 0.35 and straightness <= 0.5


def measure_kerbs(height: np.ndarray, labels: np.ndarray, model: GroundModel) -> list[Kerb]:
    """Edges of the carriageway on each side: where road meets something raised (footpath, wall, fence,
    building, vegetation or verge). Painted kerb stones are usually labelled as road, so the edge of the
    road label is the kerb line whatever lies beyond it. Vehicles and sky are not edges.

    The line's position is reliable out to KERB_MAX_RANGE_M; its height is not (a single camera smooths the
    kerb face), so a step height is only estimated next to a footpath, stored, and not shown.
    """
    h, _ = labels.shape
    z = model.distance(np.arange(h))
    rows = (z >= MIN_KERB_RANGE_M) & (z <= KERB_MAX_RANGE_M)
    rows[int(h * 0.94) :] = False
    in_range = np.repeat(rows[:, None], labels.shape[1], axis=1)
    road = (labels == ROAD) & in_range
    beyond = np.isin(labels, EDGE_CLASSES) & in_range
    if road.sum() < 400 or beyond.sum() < 200:
        return []
    k = np.ones((7, 7), np.uint8)
    road_edge = road & cv2.dilate(beyond.astype(np.uint8), k).astype(bool)
    step = max(2, h // 120)
    cx = int(model.cx)
    kerbs: list[Kerb] = []
    for is_left in (True, False):
        half = np.zeros_like(road_edge)
        if is_left:
            half[:, :cx] = True
        else:
            half[:, cx:] = True
        edge = road_edge & half
        if edge.sum() < 60:
            continue
        points = _boundary_line(edge, is_left, step)
        if len(points) < 5 or not _runs_along_road(points, model):
            continue
        # What lies beyond the edge, and a footpath step height when there is one.
        near = cv2.dilate(edge.astype(np.uint8), k).astype(bool) & half
        outside = labels[near & np.isin(labels, EDGE_CLASSES)]
        beyond_cls = int(np.bincount(outside, minlength=19).argmax()) if outside.size else -1
        drop = None
        if beyond_cls == SIDEWALK:
            top = height[near & (labels == SIDEWALK) & range_mask(labels.shape, model)]
            bottom = height[edge & range_mask(labels.shape, model)]
            top, bottom = top[np.isfinite(top)], bottom[np.isfinite(bottom)]
            if top.size >= 40 and bottom.size >= 40:
                drop = float(np.median(bottom) - np.median(top)) * 100
        ground = np.array([model.to_ground(float(x), float(y)) for x, y in points])
        kerbs.append(
            Kerb(
                drop_cm=drop,
                side="left" if is_left else "right",
                points=points,
                samples=int(edge.sum()),
                beyond=EDGE_NAMES.get(beyond_cls, "edge"),
                ground=ground,
            )
        )
    return kerbs
