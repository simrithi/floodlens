#!/usr/bin/env bash
# Publish a finished survey to the live site: everything the UI reads under /analysis/.
#
#   bash backend/scripts/publish_site.sh 3827609 lth bengaluru
#   bash backend/scripts/publish_site.sh 4020141 full delhi
#
# What it does, in order:
#   1. copies every finished survey's analysis.json from the outputs bucket to data/outputs/
#   2. builds the flow lines locally (export_flow.py, from the bare-earth DEM)
#   3. rebuilds the city's findings (build_findings.py), from every analysed survey of that city found locally
#   4. copies frames, overlays and depth maps from the outputs bucket to the site bucket, server side, and
#      uploads analysis.json, flow.geojson and the findings with the right content types
#   5. invalidates the CloudFront cache for /analysis/*
#
# Needs AWS credentials, Python with the backend requirements, and the data/geo rasters.
set -euo pipefail

SEQ=${1:?sequence id}
SIZE=${2:?lth or full}
CITY=${3:?delhi or bengaluru}
ACCOUNT=563469689377
OUT_BUCKET=floodlens-outputs-$ACCOUNT
SITE_BUCKET=floodlensweb-sitebucket397a1860-lklujpasrixv
DIST_ID=E27HTQ0D9GRDDR
PREFIX=$SEQ-$SIZE
LOCAL=$(cd "$(dirname "$0")/../.." && pwd)/data/outputs
export AWS_PAGER=""

# findings are built from every finished 1280p survey, so pull each one that exists
for P in $(aws s3 ls "s3://$OUT_BUCKET/" | grep -oE '[0-9]+-lth' | sort -u) "$PREFIX"; do
  if aws s3 ls "s3://$OUT_BUCKET/$P/analysis.json" >/dev/null 2>&1; then
    mkdir -p "$LOCAL/$P"
    aws s3 cp "s3://$OUT_BUCKET/$P/analysis.json" "$LOCAL/$P/analysis.json" --quiet
  fi
done

cd "$(dirname "$0")/.."
python scripts/export_flow.py --sequence "$SEQ" --size "$SIZE"
python scripts/build_findings.py --city "$CITY"

SITE=s3://$SITE_BUCKET/analysis
for d in frames overlays depth; do
  aws s3 sync "s3://$OUT_BUCKET/$PREFIX/$d/" "$SITE/$PREFIX/$d/" --quiet
done
aws s3 cp "$LOCAL/$PREFIX/analysis.json" "$SITE/$PREFIX/analysis.json" --content-type application/json --quiet
aws s3 cp "$LOCAL/$PREFIX/flow.geojson" "$SITE/$PREFIX/flow.geojson" --content-type application/geo+json --quiet
[ -f "$LOCAL/$PREFIX/kerb_lines.geojson" ] && aws s3 cp "$LOCAL/$PREFIX/kerb_lines.geojson" "$SITE/$PREFIX/kerb_lines.geojson" --content-type application/geo+json --quiet || true
aws s3 cp "$LOCAL/findings-$CITY.json" "$SITE/findings-$CITY.json" --content-type application/json --quiet
# The Lambdas (frame check, forecast) read the findings and analysis from the outputs bucket too.
aws s3 cp "$LOCAL/findings-$CITY.json" "s3://$OUT_BUCKET/analysis/findings-$CITY.json" --content-type application/json --quiet

MSYS_NO_PATHCONV=1 aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/analysis/*" --query Invalidation.Status --output text
echo "published $PREFIX ($CITY)"
