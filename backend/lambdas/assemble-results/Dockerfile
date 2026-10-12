# Build from backend/ as context, so this can see both core/ and this folder:
#   docker build -f lambdas/assemble-results/Dockerfile -t floodlens-assemble .
FROM public.ecr.aws/lambda/python:3.12

# rasterio's bundled GDAL needs libexpat (XML parsing), not present on the minimal base image.
RUN dnf install -y expat && dnf clean all

COPY lambdas/assemble-results/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ core/
COPY lambdas/assemble-results/handler.py .

# Pre-built hydrology rasters (scripts/build_hydrology.py --city delhi): unlike the DEM tile,
# these don't self-download, so they're baked into the image here, read-only, and handler.py
# copies them into /tmp at cold start (Lambda's /tmp is fresh per execution environment --
# anything baked into /tmp at build time is NOT what the running container sees).
COPY lambdas/assemble-results/seed-hydro-delhi/ seed/hydro-delhi/
COPY lambdas/assemble-results/seed-hydro-bengaluru/ seed/hydro-bengaluru/
COPY lambdas/assemble-results/seed-geo-bengaluru/ seed/geo-bengaluru/

# Lambda's only writable path is /tmp; the DEM tile and rainfall cache land there too.
ENV FLOODLENS_DATA_DIR=/tmp/data

CMD ["handler.handler"]
