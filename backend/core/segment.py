"""Semantic segmentation: which pixels are road, which are footpath (sidewalk)."""

import numpy as np
import torch
import torch.nn.functional as F

from .models import device, segformer


@torch.inference_mode()
def segment(image: np.ndarray) -> np.ndarray:
    """Return an HxW uint8 map of Cityscapes class ids (0 road, 1 sidewalk, 13 car, ...)."""
    processor, model = segformer()
    inputs = processor(images=image, return_tensors="pt").to(device())
    logits = model(**inputs).logits  # (1, 19, h/4, w/4)
    logits = F.interpolate(logits, size=image.shape[:2], mode="bilinear", align_corners=False)
    return logits.argmax(dim=1)[0].to(torch.uint8).cpu().numpy()
