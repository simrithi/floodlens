# Varshik on AWS: submission notes

What is deployed in account 563469689377, region us-east-1. Claims here match what was checked in the account.

## Where AWS fits (for the write-up)

Varshik finds the roads likely to hold water before the rain arrives. A single Amazon SageMaker real-time endpoint on a GPU instance serves its three vision models (SegFormer-B2, Depth Anything V2, YOLOv8m-seg). AWS Step Functions sends every dashcam frame of a survey to it through a Lambda function, and a second Lambda assembles the per-frame results with terrain from the AWS Registry of Open Data (Copernicus GLO-30), road profiles from the phone's tilt sensor and a water-balance model into stretches of about 60 m. Amazon Bedrock (Amazon Nova Lite) reads the dashcam frames of each flagged spot for what is visible at the drain, and writes a one-page brief for the drainage engineer in English or Hindi; the brief is rejected unless every number in it appears in the findings. A daily Amazon EventBridge Scheduler job reads tomorrow's rain forecast, interpolates each spot's depth-versus-rain curve and sends an Amazon SNS alert. Officer approvals and on-the-ground reports are stored in Amazon DynamoDB so predictions can be checked against what happened. The web app is served from Amazon S3 through Amazon CloudFront, with infrastructure defined in AWS CDK. AI outputs are decision-support signals for an engineer to verify on site, never inputs to the water model.

## 30-second script for the AWS section of the video

1. (0-8 s) Console, SageMaker: "All three vision models run on one GPU endpoint, `floodlens-analyze`. Step Functions feeds it a frame at a time." Show the endpoint InService and the `floodlens-pipeline` execution graph.
2. (8-18 s) Console, Lambda logs for `floodlens-frame-check`: "Bedrock Nova Lite looks at the dashcam frames of a flagged spot and reports whether a drain inlet is visible. It is evidence to verify, not a score." Show the JSON in the log.
3. (18-25 s) The SNS alert email or the alert JSON in S3: "Every evening EventBridge runs the forecast Lambda; if tomorrow's rain would put 5 cm or more on a spot, it alerts the officer."
4. (25-30 s) CloudFront URL: "S3 and CloudFront serve the app. Officers approve actions and report what happened; DynamoDB keeps it so we can measure how right we were."

Record the SNS email only after the subscription has been confirmed (see below).

## What is deployed

| Resource | Name | Purpose |
|---|---|---|
| S3 | `floodlens-raw-563469689377`, `floodlens-outputs-563469689377`, `floodlensweb-sitebucket...` | raw frames, analysis outputs, the web app |
| CloudFront | stack `FloodLensWeb` | HTTPS delivery, d24wvc44c3vaxz.cloudfront.net |
| SageMaker | endpoint `floodlens-analyze`, 1 x ml.g4dn.xlarge | the three vision models |
| Step Functions | `floodlens-pipeline` | per-frame analysis, then assemble |
| Lambda (9) | `floodlens-start-run`, `get-upload-url`, `get-run-status`, `invoke-frame`, `assemble-results`, `frame-check`, `officer-brief`, `forecast`, `actions` | pipeline workers and the AI features |
| Lambda Function URLs (3, public) | `frame-check`, `officer-brief`, `actions` | called by the web app, CORS limited to the CloudFront domain |
| Bedrock | `us.amazon.nova-lite-v1:0` | frame check and officer brief |
| EventBridge Scheduler | `floodlens-daily-forecast` | 17:00 IST daily |
| SNS | `floodlens-alerts` | alerts (the email subscription must be confirmed by its owner) |
| DynamoDB | `floodlens-runs`, `FloodLensActions` | run status, officer actions and observations |
| ECR | `floodlens-serve`, `floodlens-assemble` | container images |
| SSM Parameter Store | `/floodlens/officer-passcode` (SecureString) | officer passcode, set by the owner in the console |
| CloudWatch | error alarms per Lambda, `floodlens-bedrock-throttles` | monitoring |
| Budgets | `FloodLens-Monthly` | spend alerts |

## Cost at demo usage

| Item | Estimate | Note |
|---|---|---|
| SageMaker endpoint | about US$0.74 per hour (about US$530 per month) while running | ml.g4dn.xlarge on-demand list price in us-east-1; check the current price. This dominates everything else. |
| Bedrock Nova Lite | well under US$0.01 per frame check or brief | priced per token; a few images and about a page of text per call |
| Lambda, DynamoDB, SNS, EventBridge, Step Functions | cents at demo volume | all within or near free tier |
| S3, CloudFront | cents | small data volume |

The endpoint is the only large cost. Delete it when judging is over, or leave it running only if the analysis must be re-run.

## Limits on public cost

- `frame-check`: at most 30 fresh checks per hour overall, a counter in S3 (the limiter was unit-tested: 30 allowed, the 31st blocked). Cached results are served without a model call.
- `officer-brief`: cached by a hash of the findings, so a brief is regenerated only when the findings change. It has no per-hour limit; `refresh` requests are the only way to force a new generation.
- `actions` writes need the officer passcode, and refuse all writes until it is set.

## Tear down

1. Delete the endpoint first (it is the cost): `aws sagemaker delete-endpoint --endpoint-name floodlens-analyze`, then the endpoint config `floodlens-analyze-config` and the model `floodlens-analyze`.
2. `cd infra && npx cdk destroy FloodLensWeb` removes the site bucket and CloudFront (empty the bucket first if destroy refuses).
3. Not removed by CDK, delete by hand: the nine Lambda functions and their Function URLs, state machine `floodlens-pipeline`, DynamoDB tables `floodlens-runs` and `FloodLensActions`, SNS topic `floodlens-alerts`, schedule `floodlens-daily-forecast`, ECR repositories `floodlens-serve` and `floodlens-assemble`, S3 buckets `floodlens-raw-...` and `floodlens-outputs-...` (empty them first), SSM parameter `/floodlens/officer-passcode`, the CloudWatch alarms, the budget, the IAM roles `floodlens-lambda-execution` and the Step Functions and scheduler roles.

## Known limits

- Kannada was tried and removed: the machine translation was not good enough (it mistranslated place names and "ward"). It is future scope. The Hindi brief is machine-written and should be reviewed by a fluent reader.
- The forecast uses hourly rain as the input to curves built from 15-minute design storms, because no sourced conversion ratio exists. Every alert says so.
- All validation figures are preliminary. See the README.
