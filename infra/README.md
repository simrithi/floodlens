# infra: the web stack (AWS CDK v2, TypeScript)

This folder defines **one stack, `FloodLensWeb`**: the private S3 bucket and the CloudFront distribution that serve the app and its analysis files. It does not define the rest of the AWS setup.

## What is in CDK

| Resource | Notes |
|---|---|
| S3 bucket (site) | Private, all public access blocked, S3-managed encryption, retained on delete |
| CloudFront distribution | Origin Access Control to the bucket, HTTPS only, HTTP/2 and 3, compression |
| CloudFront Function | Rewrites extensionless paths (`/map`, `/report/delhi`) to `/index.html`. There are deliberately no 403/404 error-page rewrites, which would hide a missing analysis file |
| Cache policies | `index.html` no-cache; hashed `assets/*` one year; `analysis/*.json` and `*.geojson` five minutes; analysis images one day |
| Tags | `Project=FloodLens` on everything in this stack |

## What is not in CDK (created with the AWS CLI)

The pipeline and AI backend were created by hand with the CLI and the JSON policy files in [`../backend/lambdas/`](../backend/lambdas/): the SageMaker endpoint, the Step Functions state machine, the nine Lambda functions and their Function URLs, DynamoDB tables, the SNS topic, the EventBridge schedule, ECR repositories and IAM roles. Putting them in CDK is the main piece of infrastructure work still open, and it would also let the one shared Lambda role be split into a role per function. See [`../docs/AWS_SUBMISSION.md`](../docs/AWS_SUBMISSION.md) for the resource list and teardown steps.

## Commands

```bash
npm install
npm test            # 5 tests on the template: private bucket, OAC and HTTPS, SPA routing, caching, tags
npx cdk diff        # compare with the deployed stack
npx cdk deploy      # deploy FloodLensWeb (us-east-1)
```

Deploying the app itself is separate: `bash deploy.sh` builds [`../ui/`](../ui/), uploads it to the site bucket and invalidates the cache; publish analysis data with [`../backend/scripts/publish_site.sh`](../backend/scripts/publish_site.sh).
