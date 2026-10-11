"""Street-view overlay images: predicted water, potholes and kerb drawn on the dashcam frame."""

from pathlib import Path

import cv2
import numpy as np

from .analyze import FrameAnalysis

# BGR versions of the UI design tokens (ui/DESIGN.md).
WATER = (255, 154, 76)  # #4c9aff
POTHOLE = (68, 68, 239)  # #ef4444
KERB = (21, 204, 250)  # #facc15
INK = (248, 248, 247)
PANEL = (17, 16, 15)


def _label(img: np.ndarray, text: str, org: tuple[int, int], color: tuple[int, int, int], scale: float) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    thick = max(1, round(scale * 2))
    (tw, th), base = cv2.getTextSize(text, font, scale, thick)
    x, y = org
    x = int(np.clip(x, 4, img.shape[1] - tw - 16))
    y = int(np.clip(y, th + 12, img.shape[0] - 8))
    pad = round(6 * scale / 0.6)
    cv2.rectangle(img, (x - pad, y - th - pad), (x + tw + pad, y + base + pad // 2), PANEL, -1)
    cv2.rectangle(img, (x - pad, y - th - pad), (x - pad + 4, y + base + pad // 2), color, -1)
    cv2.putText(img, text, (x + 2, y), font, scale, INK, thick, cv2.LINE_AA)


def render_overlay(image_rgb: np.ndarray, a: FrameAnalysis) -> np.ndarray:
    """Return a BGR image with the frame's findings drawn on it."""
    img = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    scale = img.shape[1] / 1280 * 0.55
    layer = img.copy()

    for dip in a.dips:
        cv2.fillPoly(layer, [dip.polygon], WATER)
    img = cv2.addWeighted(layer, 0.42, img, 0.58, 0)
    for dip in a.dips:
        cv2.polylines(img, [dip.polygon], True, WATER, max(1, round(2 * scale / 0.55)), cv2.LINE_AA)
        _label(img, f"dip {dip.depth_cm:.0f} cm  {dip.area_m2:.1f} m2", (dip.centroid[0] - 40, dip.centroid[1] - 12), WATER, scale)

    for p, depth in zip(a.potholes, a.pothole_depth_cm):
        cv2.polylines(img, [p.polygon], True, POTHOLE, max(2, round(3 * scale / 0.55)), cv2.LINE_AA)
        _label(img, f"pothole {p.confidence:.0%}  {depth:.0f} cm", (p.bbox[0], p.bbox[1] - 10), POTHOLE, scale)

    for kerb in a.kerbs:
        if len(kerb.points) > 1:
            cv2.polylines(img, [kerb.points.reshape(-1, 1, 2)], False, KERB, max(2, round(3 * scale / 0.55)), cv2.LINE_AA)
            top = kerb.points[0]
            _label(img, "kerb", (int(top[0]), int(top[1]) - 14), KERB, scale)

    return img


def render_depth(a: FrameAnalysis) -> np.ndarray | None:
    """Colour-mapped disparity (near = warm) for the UI's 'AI depth view' toggle."""
    if a.disparity is None:
        return None
    d = a.disparity
    lo, hi = np.percentile(d, [2, 98])
    norm = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
    return cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_TURBO)


def save_jpeg(path: Path, bgr: np.ndarray, quality: int = 86) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
