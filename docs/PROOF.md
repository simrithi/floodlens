# Proof that the AWS services are live

Everything is deployed in `us-east-1`. This page records evidence, and a script anyone with access to the account can re-run to check it again. The account number is replaced by `<account>`.

> *Note (16 October 2026): the SageMaker endpoint was deleted after submission to avoid idle cost (about US$0.74 an hour). The model, the endpoint configuration and the container image are kept, and one command recreates it in about 10 minutes. The checks recorded here were made on 12 October while it was running.*
>
> ```bash
> aws sagemaker create-endpoint --endpoint-name floodlens-analyze --endpoint-config-name floodlens-analyze-config --region us-east-1
> ```

## 1. Re-run the checks yourself

```bash
bash infra/verify_aws.sh
```

It is read-only: it changes nothing, calls no paid model, and never reads the passcode. It exits non-zero if any check fails.

## 2. Result of that script on 12 October 2026 (05:56 IST)

```text
Account <account>, region us-east-1, 2026-10-12T00:26:00Z

PASS  CloudFront /                 200
PASS  CloudFront /map              200
PASS  CloudFront /report/delhi     200
PASS  CloudFront /report/bengaluru 200
PASS  site /analysis/findings-delhi.json 200
PASS  site /analysis/findings-bengaluru.json 200
PASS  site /analysis/4020141-lth/analysis.json 200
PASS  site /analysis/4020141-full/analysis.json 200
PASS  site /analysis/3827609-lth/analysis.json 200
PASS  site /analysis/9316057-lth/analysis.json 200
PASS  CloudFront distribution      Deployed
PASS  S3 public access blocked     floodlens-raw-<account>
PASS  S3 public access blocked     floodlens-outputs-<account>
PASS  S3 public access blocked     floodlensweb-sitebucket397a1860-lklujpasrixv
PASS  SageMaker endpoint           floodlens-analyze (ml.g4dn.xlarge)
PASS  Step Functions               floodlens-pipeline
PASS  EventBridge rule             floodlens-frames-uploaded
PASS  EventBridge Scheduler        cron(0 17 * * ? *) Asia/Kolkata
PASS  Lambda floodlens-start-run   Active/Successful
PASS  Lambda floodlens-get-upload-url Active/Successful
PASS  Lambda floodlens-get-run-status Active/Successful
PASS  Lambda floodlens-invoke-frame Active/Successful
PASS  Lambda floodlens-assemble-results Active/Successful
PASS  Lambda floodlens-frame-check Active/Successful
PASS  Lambda floodlens-officer-brief Active/Successful
PASS  Lambda floodlens-forecast    Active/Successful
PASS  Lambda floodlens-actions     Active/Successful
PASS  Function URL frame-check     public, called by the browser
PASS  Function URL officer-brief   public, called by the browser
PASS  Function URL actions         public, called by the browser
PASS  Bedrock access (Nova)        Nova Lite and Nova Pro only
PASS  DynamoDB floodlens-runs      ACTIVE
PASS  DynamoDB FloodLensActions    ACTIVE
PASS  SNS subscription             confirmed (email)
PASS  SSM officer passcode         value not read
PASS  ECR floodlens-serve          8 images
PASS  ECR floodlens-assemble       10 images
PASS  CloudWatch alarms            10 alarms (0 currently in ALARM)
PASS  Log retention 14 days        every floodlens log group
PASS  AWS Budget                   FloodLens-Monthly, US$25

All checks passed.
```

40 of 40 checks passed.

## 3. A real alarm email through SNS

The SNS topic `floodlens-alerts` has a confirmed email subscription, and CloudWatch alarms publish to it. To prove the whole path, I ran a pipeline execution that was made to fail on purpose (a frame that does not exist). The `floodlens-invoke-frame-errors` alarm fired and AWS emailed the subscriber:

| Field | Value |
|---|---|
| Subject | `ALARM: "floodlens-invoke-frame-errors" in US East (N. Virginia)` |
| From | AWS Notifications `<no-reply@sns.amazonaws.com>` |
| Received | 5:24 AM IST (Sunday 11 October 2026, 23:54:53 UTC) |
| State change | OK -> ALARM |
| Reason | Threshold Crossed: 1 datapoint [1.0 (11/10/26 23:49:00)] was greater than or equal to the threshold (1.0) |
| Monitored metric | `AWS/Lambda` `Errors`, `FunctionName = floodlens-invoke-frame`, Sum over 300 seconds, missing data not breaching |
| Alarm action | `ALARM: [arn:aws:sns:us-east-1:<account>:floodlens-alerts]` |
| Alarm ARN | `arn:aws:cloudwatch:us-east-1:<account>:alarm:floodlens-invoke-frame-errors` |

The same test also showed the pipeline now fails properly: the Step Functions execution ended `FAILED` (`PipelineFailed`) and the run record in DynamoDB said `failed`.

Not yet observed: the daily flood-alert email itself (the forecast Lambda's message). It runs at 17:00 IST and only sends when tomorrow's forecast reaches 5 cm at a spot. A forced test run produced the correct alert file (Delhi S1 14.0 cm at 100 mm/hr), but its email was not captured.

## 4. What each service does and how it was checked

| Service | Live evidence |
|---|---|
| Amazon SageMaker | Endpoint `floodlens-analyze` is InService on `ml.g4dn.xlarge`. A real inference through the `invoke-frame` Lambda returned a full frame record (road regions, relative depth, kerbs, overlay and depth images) (stopped on 16 October to save cost; see the note at the top) |
| AWS Step Functions | `floodlens-pipeline` is active. It processed the Bengaluru ORR survey (422 frames), Bellandur (133) and Delhi at 4K (207). A forced failure ends `FAILED` |
| AWS Lambda | All nine functions are Active with a successful last update; three have public Function URLs |
| Amazon Bedrock | Fresh frame checks on all 6 current spots returned valid answers from Nova Lite; fresh English and Hindi briefs for both cities passed verification (Nova Lite and Nova Pro) |
| Amazon EventBridge | The rule `floodlens-frames-uploaded` is enabled; the Scheduler job runs `cron(0 17 * * ? *)` in Asia/Kolkata |
| Amazon SNS | Email subscription confirmed; an alarm email was delivered (section 3) |
| Amazon DynamoDB | `floodlens-runs` and `FloodLensActions` are ACTIVE |
| AWS Systems Manager | `/floodlens/officer-passcode` exists as a SecureString (value never read); wrong passcodes are refused with 401 |
| Amazon S3 | Three buckets, public access blocked on all |
| Amazon CloudFront | Distribution deployed; the four app routes and the analysis files return 200 |
| Amazon ECR | `floodlens-serve` and `floodlens-assemble` hold container images |
| Amazon CloudWatch | 10 alarms (an error alarm per Lambda and one for Bedrock throttling), none in ALARM; every log group keeps 14 days |
| AWS Budgets | `FloodLens-Monthly`, US$25, alerts at 50%, 80% and 100% |
| AWS Registry of Open Data | Copernicus GLO-30 elevation used in the terrain analysis |
| AWS CDK | The web stack (S3 and CloudFront) with 5 passing template tests; the rest was created with the AWS CLI |

The detailed list of tests, including attempts to break the public endpoints, is in the README under "Tests and verification".
