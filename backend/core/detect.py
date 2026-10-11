"""Pothole instance segmentation with YOLOv8."""

from dataclasses import dataclass

import cv2
import numpy as np

from .models import device, pothole_model


@dataclass
class Pothole:
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in image pixels
    polygon: np.ndarray  # (N, 2) int32 outline in image pixels
    mask: np.ndarray  # HxW bool


def detect_potholes(image: np.ndarray, min_confidence: float = 0.35) -> list[Pothole]:
    """Find potholes in an RGB image. Returns one entry per pothole with its pixel mask."""
    h, w = image.shape[:2]
    imgsz = max(640, min(1920, (w // 32) * 32))
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    result = pothole_model().predict(
        bgr, imgsz=imgsz, conf=min_confidence, device=0 if device() == "cuda" else "cpu", verbose=False
    )[0]
    if result.masks is None:
        return []

    found = []
    for poly, box, conf in zip(result.masks.xy, result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
        if len(poly) < 3:
            continue
        polygon = np.round(poly).astype(np.int32)
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [polygon], 1)
        x1, y1, x2, y2 = (int(v) for v in box)
        found.append(Pothole(float(conf), (x1, y1, x2, y2), polygon, mask.astype(bool)))
    return found
