"""Semantic segmentation: which pixels are road, which are footpath (sidewalk)."""

import numpy as np
import torch
import torch.nn.functional as F

from .config import ROAD
from .models import device, segformer


@torch.inference_mode()
def segment(image: np.ndarray) -> np.ndarray:
    """Return an HxW uint8 map of Cityscapes class ids (0 road, 1 sidewalk, 13 car, ...)."""
    processor, model = segformer()
    inputs = processor(images=image, return_tensors="pt").to(device())
    logits = model(**inputs).logits  # (1, 19, h/4, w/4)
    logits = F.interpolate(logits, size=image.shape[:2], mode="bilinear", align_corners=False)
    return logits.argmax(dim=1)[0].to(torch.uint8).cpu().numpy()


# Pixels that must never count as road: the car's own bonnet, and road-coloured surfaces beyond the road's
# farthest point (an underpass ceiling, a flyover deck). Not a Cityscapes id.
EGO = 255
HOOD_MAX_FRACTION = 0.4


def sequence_hood_fraction(rows: list[int], height: int, visible: float = 0.10, margin: float = 0.015) -> float | None:
    """The bonnet is fixed to the camera, so take the median edge over sample frames of a sequence. Returns the
    share of the frame to drop (plus a margin, depth bleeds across the edge), or None when no bonnet is
    visible beyond the dashboard sliver every phone mount has (Camera.hood_fraction covers that)."""
    share = 1 - float(np.median(rows)) / height
    return share + margin if share >= visible else None


def own_vehicle_row(labels: np.ndarray, disparity: np.ndarray | None = None, road_share: float = 0.25) -> int:
    """First image row of the car's own bonnet/dashboard, or the frame height if none is visible.

    Two cues, whichever finds the higher edge: (1) a band at the bottom where the road does not show across
    the central half; (2) a bonnet that the segmenter calls road (grey paint), found in the depth map as a
    sudden jump in disparity between road and bonnet. On a flat road disparity grows steadily down the
    frame, so a jump many times the usual row-to-row step is an edge, not road."""
    h, w = labels.shape
    lo = int(h * (1 - HOOD_MAX_FRACTION))
    share = (labels[:, w // 4 : 3 * w // 4] == ROAD).mean(axis=1)
    row = h
    while row > lo and share[row - 1] < road_share:
        row -= 1
    row = row if row < h - 2 else h
    if disparity is not None:
        m = np.median(disparity[:, w // 4 : 3 * w // 4], axis=1)
        k = max(2, int(0.02 * h))
        jump = m[k:] - m[:-k]  # jump[r] = m[r + k] - m[r]
        usual = np.median(np.abs(np.diff(m[int(0.55 * h) : lo]))) * k + 1e-6
        r = lo + int(np.argmax(jump[lo : h - k]))
        if jump[r] > max(5 * usual, 1.0):
            row = min(row, r)
    return row


def clean_labels(labels: np.ndarray, disparity: np.ndarray | None = None, hood_row: int | None = None) -> np.ndarray:
    """Mark the own vehicle and detached 'road' (ceilings, decks) as EGO so no stage measures them.

    hood_row: first row of the bonnet for this sequence (see sequence_hood_fraction); None = no bonnet."""
    out = labels.copy()
    h = labels.shape[0]
    hood = h if hood_row is None else min(h, hood_row)
    if hood < h:
        out[hood:] = EGO
    if disparity is not None:
        # Road ends at its farthest point, the row of least disparity. Anything labelled road above it
        # comes nearer again: an underpass ceiling or flyover deck, not road.
        m = np.median(disparity[:, labels.shape[1] // 4 : 3 * labels.shape[1] // 4], axis=1)
        far = int(np.argmin(m[: int(0.75 * h)]))
        out[:far][out[:far] == ROAD] = EGO
    return out
