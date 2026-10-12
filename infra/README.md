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

## Deploying from GitHub Actions

`.github/workflows/deploy.yaml` is a manual workflow (Actions, then deploy, then Run workflow) that builds the app, uploads it and invalidates the cache. It is not configured yet, and fails with a clear message until it is. One-time setup:

1. In AWS IAM, add the GitHub OIDC identity provider (`token.actions.githubusercontent.com`) and a role that trusts only this repository's `main` branch.
2. Give the role only what `deploy.sh` needs: `s3:PutObject`, `s3:ListBucket` and `s3:DeleteObject` on the site bucket's `assets/` and root files, and `cloudfront:CreateInvalidation` on the distribution.
3. In the repository settings, create an environment named `production` and add the variables `AWS_DEPLOY_ROLE_ARN`, `VITE_API_FRAME_CHECK`, `VITE_API_BRIEF` and `VITE_API_ACTIONS`. No secrets are needed.

## Checking the deployment

`bash verify_aws.sh` is a read-only check of every service (live routes, SageMaker, Step Functions, Lambda, EventBridge, SNS, DynamoDB, S3, CloudFront, ECR, alarms, budget). It prints PASS or FAIL for each and changes nothing. Its recorded output is in [`../docs/PROOF.md`](../docs/PROOF.md).

## Commands

```bash
npm install
npm test            # 5 tests on the template: private bucket, OAC and HTTPS, SPA routing, caching, tags
npx cdk diff        # compare with the deployed stack
npx cdk deploy      # deploy FloodLensWeb (us-east-1)
```

Deploying the app itself is separate: `bash deploy.sh` builds [`../ui/`](../ui/), uploads it to the site bucket and invalidates the cache; publish analysis data with [`../backend/scripts/publish_site.sh`](../backend/scripts/publish_site.sh).
