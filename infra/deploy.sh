#!/usr/bin/env bash
# Rebuild the web app and publish it: build, upload to the site bucket, invalidate the cache.
#   bash infra/deploy.sh
# The analysis files under /analysis are published separately (backend/scripts/publish_site.sh) and are not touched here.
# Needs AWS credentials, Node 22, and ui/.env.production (the Function URLs; see ui/README.md).
set -euo pipefail

SITE_BUCKET=floodlensweb-sitebucket397a1860-lklujpasrixv
DIST_ID=E27HTQ0D9GRDDR
export AWS_PAGER=""
cd "$(dirname "$0")/../ui"

npm ci
npm run build

# Hashed assets can be cached for a year; index.html must never be.
aws s3 sync dist/assets "s3://$SITE_BUCKET/assets" --cache-control "public,max-age=31536000,immutable"
for f in favicon.svg logo.svg icons.svg; do
  [ -f "dist/$f" ] && aws s3 cp "dist/$f" "s3://$SITE_BUCKET/$f" --content-type image/svg+xml
done
aws s3 cp dist/index.html "s3://$SITE_BUCKET/index.html" --cache-control "no-cache" --content-type text/html

MSYS_NO_PATHCONV=1 aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/index.html" "/favicon.svg" "/logo.svg" --query Invalidation.Status --output text
echo "deployed: https://d24wvc44c3vaxz.cloudfront.net/"
