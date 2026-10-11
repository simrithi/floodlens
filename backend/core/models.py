"""Lazy, cached loading of the three neural networks. Each loads once per process."""

import shutil
from functools import lru_cache

import torch

from .config import DEPTH_REPO, MODELS_DIR, POTHOLE_REPO, SEGFORMER_REPO


def device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def pothole_weights_path():
    return MODELS_DIR / "yolo" / "pothole-seg.pt"


@lru_cache(maxsize=1)
def pothole_model():
    """YOLOv8 instance segmentation trained to find potholes."""
    from huggingface_hub import hf_hub_download
    from ultralytics import YOLO

    path = pothole_weights_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(hf_hub_download(POTHOLE_REPO, "best.pt"), path)
    return YOLO(str(path))


@lru_cache(maxsize=1)
def segformer():
    """SegFormer-B2 fine-tuned on Cityscapes: per-pixel road / sidewalk / vehicle / ... labels."""
    from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor

    processor = SegformerImageProcessor.from_pretrained(SEGFORMER_REPO)
    model = SegformerForSemanticSegmentation.from_pretrained(SEGFORMER_REPO).to(device()).eval()
    return processor, model


@lru_cache(maxsize=1)
def depth_model():
    """Depth Anything V2 Small: relative inverse depth (disparity) from a single image."""
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    processor = AutoImageProcessor.from_pretrained(DEPTH_REPO)
    model = AutoModelForDepthEstimation.from_pretrained(DEPTH_REPO).to(device()).eval()
    return processor, model
