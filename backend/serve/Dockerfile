# Build from the backend/ folder as context, so this can see both requirements.txt and core/:
#   docker build -f serve/Dockerfile -t floodlens-serve .
#
# Uses a stable CUDA 12.6 PyTorch base, not the cu130 Blackwell build from the local dev setup
# (docs/APPLICATION.md "Setup"). That reinstall was only needed for an RTX 50-series laptop GPU;
# SageMaker GPU instances (T4 / A10G) are older architectures and work fine with this standard,
# officially published PyTorch image (verified against Docker Hub's actual tag list).
FROM pytorch/pytorch:2.7.1-cuda12.6-cudnn9-runtime

WORKDIR /opt/program

# opencv-python-headless still dynamically links a handful of X11/GL libraries at import time
# despite the "headless" name; the conda-based PyTorch image doesn't have them by default.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libxext6 libsm6 libxrender1 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Pipeline dependencies first (the big, slow-changing layer), then the small serving extras.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY serve/requirements.txt serve-requirements.txt
RUN pip install --no-cache-dir -r serve-requirements.txt

COPY core/ core/
COPY serve/handler.py .
COPY serve/serve /usr/local/bin/serve
RUN chmod +x /usr/local/bin/serve

# Everything the pipeline writes (DEM tile, HF model cache) stays inside the container's
# writable layer; nothing here needs to persist between invocations.
ENV FLOODLENS_DATA_DIR=/tmp/data
ENV FLOODLENS_MODELS_DIR=/opt/program/models
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# One worker: the three models are loaded once per process (core/models.py's lru_cache) and
# held on the GPU, so a second worker would double the GPU memory for no benefit. Timeout is
# generous because the first request after a cold start also downloads and loads all three
# models (can take well over the gunicorn default 30s).
#
# No CMD here on purpose: SageMaker runs `docker run <image> serve`, which would override a
# CMD entirely. The `serve` executable above is what that argument actually finds and runs.
