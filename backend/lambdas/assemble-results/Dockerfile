# Build from backend/ as context, so this can see both core/ and this folder:
#   docker build -f lambdas/assemble-results/Dockerfile -t floodlens-assemble .
FROM public.ecr.aws/lambda/python:3.12

COPY lambdas/assemble-results/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ core/
COPY lambdas/assemble-results/handler.py .

# Lambda's only writable path is /tmp; the DEM tile and rainfall cache land there.
ENV FLOODLENS_DATA_DIR=/tmp/data

CMD ["handler.handler"]
