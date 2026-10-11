"""Turning a single dashcam frame into metric road geometry.

Model: the road near the car is a plane, the camera sits `height_m` above it.
For a pinhole camera, inverse depth on a flat road is linear in the image row:

    1 / Z(y) = (y - y_h) / (f * h)            y_h = horizon row

Depth Anything returns disparity d that is an affine function of 1/Z (unknown scale k, shift s).
So on road pixels d is linear in (y, x): we fit d_g(x, y) = a*y + b*x + c robustly, which also absorbs
road camber and camera roll through the x term.

A road point that sits `delta` metres below the plane is seen along the same ray but further away:
Z = Z_g * (h + delta) / h, therefore

    delta = h * ((d_g - s) / (d - s) - 1)      (> 0: below the road surface, a dip)

and a raised surface (footpath, kerb top) gives delta < 0. With the shift s assumed ~0 the horizon is
y_h = -(c + b*cx) / a. If that lands outside a plausible band we pin the horizon and solve for s instead.
"""

import math
from dataclasses import dataclass

import numpy as np

from .config import CAMERA, MAX_RANGE_M, MIN_RANGE_M, Camera


@dataclass
class GroundModel:
    a: float
    b: float
    c: float
    shift: float
    horizon_y: float
    fx: float
    fy: float
    cx: float
    cy: float
    height_m: float
    inliers: int
    residual_std: float

    def ground_disparity(self, shape: tuple[int, int]) -> np.ndarray:
        h, w = shape
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        return self.a * yy + self.b * xx + self.c

    def distance(self, y: np.ndarray | float) -> np.ndarray | float:
        """Forward distance (m) to the road at image row y. Inf at or above the horizon."""
        dy = np.asarray(y, dtype=np.float64) - self.horizon_y
        with np.errstate(divide="ignore"):
            return np.where(dy > 1, self.fy * self.height_m / np.maximum(dy, 1e-6), np.inf)

    def to_ground(self, x: float, y: float) -> tuple[float, float]:
        """Pixel -> (forward, right) metres on the road plane, relative to the camera."""
        forward = float(self.distance(y))
        right = (x - self.cx) * forward / self.fx
        return forward, right

    def pixel_area_m2(self, y: np.ndarray) -> np.ndarray:
        """Road area covered by one pixel at row y: (Z/fx) wide by Z^2/(fy*h) deep."""
        z = self.distance(y)
        return (z / self.fx) * (z * z / (self.fy * self.height_m))


def intrinsics(width: int, height: int, camera: Camera = CAMERA) -> tuple[float, float, float, float]:
    fx = (width / 2) / math.tan(math.radians(camera.hfov_deg) / 2)
    return fx, fx, width / 2, height / 2


def analysis_rows(height: int, camera: Camera = CAMERA) -> slice:
    """Rows worth analysing: below the upper third, above the car's own dashboard."""
    return slice(int(height * 0.35), int(height * (1 - camera.hood_fraction)))


def fit_ground(disparity: np.ndarray, road: np.ndarray, camera: Camera = CAMERA, seed: int = 0) -> GroundModel | None:
    """Robust plane fit of disparity over road pixels. None if there is too little visible road."""
    h, w = disparity.shape
    rows = analysis_rows(h, camera)
    mask = np.zeros_like(road, dtype=bool)
    mask[rows] = road[rows]
    ys, xs = np.nonzero(mask)
    if ys.size < 1500:
        return None
    rng = np.random.default_rng(seed)
    if ys.size > 25_000:
        pick = rng.choice(ys.size, 25_000, replace=False)
        ys, xs = ys[pick], xs[pick]
    d = disparity[ys, xs].astype(np.float64)
    A = np.column_stack([ys, xs, np.ones_like(ys)]).astype(np.float64)

    keep = np.ones(ys.size, dtype=bool)
    for _ in range(4):
        coef, *_ = np.linalg.lstsq(A[keep], d[keep], rcond=None)
        resid = d - A @ coef
        mad = np.median(np.abs(resid[keep] - np.median(resid[keep]))) + 1e-6
        keep = np.abs(resid) < 3.0 * 1.4826 * mad
    a, b, c = coef
    if a <= 0:
        return None  # disparity must grow towards the bottom of the frame on a road

    fx, fy, cx, cy = intrinsics(w, h, camera)
    shift = 0.0
    horizon = -(c + b * cx) / a
    lo, hi = 0.25 * h, 0.70 * h
    if not lo <= horizon <= hi:
        horizon = float(np.clip(horizon, lo, hi))
        shift = a * horizon + b * cx + c

    return GroundModel(
        a=float(a), b=float(b), c=float(c), shift=float(shift), horizon_y=float(horizon),
        fx=fx, fy=fy, cx=cx, cy=cy, height_m=camera.height_m,
        inliers=int(keep.sum()), residual_std=float(np.std(resid[keep])),
    )


def surface_height(disparity: np.ndarray, model: GroundModel) -> np.ndarray:
    """Per-pixel offset from the road plane in metres. > 0 below the road (dip), < 0 above (kerb)."""
    dg = model.ground_disparity(disparity.shape) - model.shift
    d = disparity - model.shift
    out = np.full(disparity.shape, np.nan, dtype=np.float32)
    ok = (d > 1e-3) & (dg > 1e-3)
    out[ok] = model.height_m * (dg[ok] / d[ok] - 1.0)
    return out


def range_mask(shape: tuple[int, int], model: GroundModel, camera: Camera = CAMERA) -> np.ndarray:
    """Rows whose road distance is within the trusted range and above the dashboard."""
    h, w = shape
    z = model.distance(np.arange(h))
    rows = (z >= MIN_RANGE_M) & (z <= MAX_RANGE_M)
    rows[int(h * (1 - camera.hood_fraction)) :] = False
    return np.repeat(rows[:, None], w, axis=1)


def offset_latlng(lat: float, lng: float, heading_deg: float, forward_m: float, right_m: float) -> tuple[float, float]:
    """Move from the camera position by (forward, right) metres given the travel heading (deg from north)."""
    t = math.radians(heading_deg)
    east = forward_m * math.sin(t) + right_m * math.cos(t)
    north = forward_m * math.cos(t) - right_m * math.sin(t)
    return lat + north / 111_320, lng + east / (111_320 * math.cos(math.radians(lat)))
