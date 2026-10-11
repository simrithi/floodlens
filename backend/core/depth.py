"""Monocular depth: relative inverse depth (disparity) for every pixel."""

import numpy as np
import torch
import torch.nn.functional as F

from .models import depth_model, device


@torch.inference_mode()
def relative_disparity(image: np.ndarray) -> np.ndarray:
    """HxW float32 disparity. Larger = closer. Unknown scale and shift (affine-invariant)."""
    processor, model = depth_model()
    inputs = processor(images=image, return_tensors="pt").to(device())
    pred = model(**inputs).predicted_depth  # (1, h, w)
    pred = F.interpolate(pred[:, None], size=image.shape[:2], mode="bicubic", align_corners=False)
    return pred[0, 0].float().cpu().numpy()
