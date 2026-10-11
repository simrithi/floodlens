"""Frame continuity: put consecutive frames in one coordinate system and check that what they see agrees.

The road is one continuous object, so a real kerb seen in frame k must line up with the same kerb seen in
frame k+1. GPS (about +-4 m) is too coarse to line frames up, so:

1. relative_pose(): visual odometry between consecutive frames. SIFT features, essential matrix with the
   known camera intrinsics, recoverPose -> heading change and direction of travel. The step length comes
   from GPS (smoothed); a single camera cannot measure it.
2. fuse_trajectory(): least-squares blend of the visual-odometry steps with GPS positions and headings,
   giving a smooth, locally accurate path that stays anchored to GPS overall.
3. Kerb points (forward, right metres per frame) are placed in that shared frame; consecutive frames'
   kerbs on the same side are compared where they overlap and chained into continuous lines.
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .config import CAMERA, Camera
from .geometry import intrinsics

EARTH = 111_320.0


@dataclass
class RelPose:
    ok: bool
    dyaw_deg: float = 0.0  # heading change from frame a to frame b (clockwise positive, like compass heading)
    direction: tuple[float, float] = (0.0, 1.0)  # unit travel direction in a's ground frame (right, forward)
    inliers: int = 0
    dpitch_deg: float = 0.0  # nose-up rotation from frame a to frame b: the change in road grade under the car


_sift = None


def _features(gray: np.ndarray):
    global _sift
    if _sift is None:
        _sift = cv2.SIFT_create(nfeatures=4000)
    h = gray.shape[0]
    mask = np.zeros_like(gray)
    mask[: int(h * 0.92)] = 255  # ignore the car's dashboard
    return _sift.detectAndCompute(gray, mask)


def relative_pose(img_a: np.ndarray, img_b: np.ndarray, camera: Camera = CAMERA) -> RelPose:
    """Camera motion from frame a to frame b (RGB images of the same size)."""
    h, w = img_a.shape[:2]
    fx, fy, cx, cy = intrinsics(w, h, camera)
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
    ka, da = _features(cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY))
    kb, db = _features(cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY))
    if da is None or db is None or len(ka) < 50 or len(kb) < 50:
        return RelPose(False)
    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2)
    good = [m for m, n in (p for p in matches if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 40:
        return RelPose(False)
    pa = np.float32([ka[m.queryIdx].pt for m in good])
    pb = np.float32([kb[m.trainIdx].pt for m in good])
    E, mask = cv2.findEssentialMat(pa, pb, K, method=cv2.RANSAC, prob=0.999, threshold=1.0)
    if E is None or E.shape != (3, 3):
        return RelPose(False)
    n, R, t, mask = cv2.recoverPose(E, pa, pb, K, mask=mask)
    if n < 30:
        return RelPose(False, inliers=int(n))
    # x_b = R x_a + t. Camera b's centre in a's coordinates: c = -R^T t. Camera axes: x right, y down, z forward.
    c = (-R.T @ t).ravel()
    ground = np.array([c[0], c[2]])
    if np.linalg.norm(ground) < 1e-6 or c[2] <= 0:
        return RelPose(False, inliers=int(n))
    ground /= np.linalg.norm(ground)
    # Heading change: b's forward axis expressed in a's frame is R^T [0,0,1]; its sideways tilt is the yaw.
    fwd_b = R.T @ np.array([0.0, 0.0, 1.0])
    dyaw = math.degrees(math.atan2(fwd_b[0], fwd_b[2]))
    # Its vertical tilt is the pitch change (y points down, so nose-up is negative y).
    dpitch = math.degrees(math.atan2(-fwd_b[1], math.hypot(fwd_b[0], fwd_b[2])))
    return RelPose(True, dyaw_deg=dyaw, direction=(float(ground[0]), float(ground[1])), inliers=int(n), dpitch_deg=dpitch)


def to_local(lat: float, lng: float, lat0: float, lng0: float) -> tuple[float, float]:
    """(east, north) metres from a reference point."""
    return (lng - lng0) * EARTH * math.cos(math.radians(lat0)), (lat - lat0) * EARTH


def to_latlng(east: float, north: float, lat0: float, lng0: float) -> tuple[float, float]:
    return lat0 + north / EARTH, lng0 + east / (EARTH * math.cos(math.radians(lat0)))


def fuse_trajectory(
    gps_en: np.ndarray,
    gps_heading: np.ndarray,
    poses: list[RelPose | None],
    mount_yaw_deg: float = 0.0,
    sigma_gps: float = 4.0,
    sigma_vo: float = 0.4,
) -> tuple[np.ndarray, np.ndarray]:
    """Least-squares path through consecutive frames.

    gps_en: (n, 2) east/north metres; gps_heading: (n,) degrees; poses[i]: motion from frame i to i+1 (or None).
    Headings: VO heading changes tie neighbours together (1 deg), GPS headings anchor them (10 deg).
    Positions: VO steps (direction from VO, length from GPS) tie neighbours (sigma_vo per axis), GPS anchors.
    VO directions are in the camera frame; mount_yaw_deg (camera turned left of travel) converts them to the
    car's frame, so a straight drive gives a step straight along the travel heading.
    """
    m = math.radians(mount_yaw_deg)
    n = len(gps_en)
    # Headings (unwrap GPS first so differences are small).
    gh = np.degrees(np.unwrap(np.radians(gps_heading)))
    rows, rhs, wts = [], [], []
    for i, p in enumerate(poses):
        if p is not None and p.ok:
            r = np.zeros(n)
            r[i + 1], r[i] = 1, -1
            rows.append(r), rhs.append(p.dyaw_deg), wts.append(1 / 1.0)
    for i in range(n):
        r = np.zeros(n)
        r[i] = 1
        rows.append(r), rhs.append(gh[i]), wts.append(1 / 10.0)
    A, b, wv = np.array(rows), np.array(rhs), np.array(wts)
    heading = np.linalg.lstsq(A * wv[:, None], b * wv, rcond=None)[0]

    # Positions: unknowns e0, n0, e1, n1, ...
    rows, rhs, wts = [], [], []
    for i, p in enumerate(poses):
        step = float(np.linalg.norm(gps_en[i + 1] - gps_en[i]))
        if p is None or not p.ok:
            continue
        cr, cf = p.direction
        right = cr * math.cos(m) - cf * math.sin(m)  # rotate camera-frame direction into the car's frame
        fwd = cr * math.sin(m) + cf * math.cos(m)
        t = math.radians(heading[i])
        de = step * (fwd * math.sin(t) + right * math.cos(t))
        dn = step * (fwd * math.cos(t) - right * math.sin(t))
        for axis, d in ((0, de), (1, dn)):
            r = np.zeros(2 * n)
            r[2 * (i + 1) + axis], r[2 * i + axis] = 1, -1
            rows.append(r), rhs.append(d), wts.append(1 / sigma_vo)
    for i in range(n):
        for axis in (0, 1):
            r = np.zeros(2 * n)
            r[2 * i + axis] = 1
            rows.append(r), rhs.append(gps_en[i, axis]), wts.append(1 / sigma_gps)
    A, b, wv = np.array(rows), np.array(rhs), np.array(wts)
    xy = np.linalg.lstsq(A * wv[:, None], b * wv, rcond=None)[0].reshape(n, 2)
    return xy, heading


def place(points_zx: np.ndarray, en: np.ndarray, heading_deg: float) -> np.ndarray:
    """Frame-relative (forward Z, right X) metres -> (east, north) metres."""
    t = math.radians(heading_deg)
    z, x = points_zx[:, 0], points_zx[:, 1]
    east = en[0] + z * math.sin(t) + x * math.cos(t)
    north = en[1] + z * math.cos(t) - x * math.sin(t)
    return np.column_stack([east, north])


def lateral_gap(line_a: np.ndarray, line_b: np.ndarray, heading_deg: float) -> float | None:
    """Median sideways distance between two placed kerb lines where they overlap along the road."""
    t = math.radians(heading_deg)
    fwd = np.array([math.sin(t), math.cos(t)])
    right = np.array([math.cos(t), -math.sin(t)])
    sa, sb = line_a @ fwd, line_b @ fwd
    lo, hi = max(sa.min(), sb.min()), min(sa.max(), sb.max())
    if hi - lo < 1.5:
        return None
    grid = np.linspace(lo, hi, 12)
    order_a, order_b = np.argsort(sa), np.argsort(sb)
    xa = np.interp(grid, sa[order_a], (line_a @ right)[order_a])
    xb = np.interp(grid, sb[order_b], (line_b @ right)[order_b])
    return float(np.median(np.abs(xa - xb)))
