# lambdas: the AWS workers around the SageMaker endpoint

Region `us-east-1`. Each folder holds a `handler.py`; the JSON files beside them are the IAM, trust and state-machine definitions used when creating the resources with the AWS CLI. These are not in CDK; see [`../../infra/README.md`](../../infra/README.md).

| Function | Trigger | Does |
|---|---|---|
| `start-run` | EventBridge, when a survey's `frames.json` lands in the raw bucket | Creates the run's DynamoDB row and starts the pipeline for the 1280p size. A 4K run is started by hand with `stepfunctions start-execution` |
| `get-upload-url` | Function URL (returns 403 and is not used by the app; it hands out presigned upload links, so it stays closed until it has authentication) | Presigned S3 upload for footage |
| `get-run-status` | Function URL (returns 403 and is not used by the app) | Reads a run's status from `floodlens-runs` |
| `invoke-frame` | Step Functions Map | Calls the SageMaker endpoint for one frame, saves the full record to S3 (`frame-records/`) and returns a pointer, because a state is limited to 256 KB |
| `assemble-results` | Step Functions | Builds `analysis.json` from the saved records: cells, terrain, drains, water depth. Container image; 3 GB, 15 minutes |
| `frame-check` | Function URL | Bedrock Nova Lite reads a spot's dashcam frames: is a drain inlet visible, is it blocked. Evidence only; 30 fresh checks per hour |
| `officer-brief` | Function URL | Bedrock brief in English or Hindi. Rejected unless every number and spot id checks out; names are added by code; 20 fresh briefs per hour |
| `forecast` | EventBridge Scheduler, 17:00 IST | Tomorrow's rain from Open-Meteo against each spot's depth curve; writes the alert and publishes to SNS |
| `actions` | Function URL | Officer approvals and ground reports in DynamoDB; writes need the passcode in SSM |

State machine: [`state-machine.json`](state-machine.json) (`floodlens-pipeline`): a serial Map over frames, then Assemble. A failure goes to `MarkFailed`, which writes `failed` to `floodlens-runs`, and then to a `RunFailed` Fail state, so Step Functions shows FAILED. (Earlier versions ended cleanly and showed SUCCEEDED for a failed run.) A good run leaves `<sequence>-<size>/analysis.json`.

## Notes

- All nine functions share one execution role (`floodlens-lambda-execution`, see `execution-policy.json`). Splitting it per function is open work. Timeouts: `frame-check` 90 s, `officer-brief` 180 s, `invoke-frame` 180 s, `assemble-results` 15 minutes.
- Cached results from `frame-check`, `officer-brief` and `forecast` are written to the outputs bucket and copied to the site bucket (`SITE_BUCKET`) so the app can read them.
- The Function URLs are public by design, since the browser calls them. Limits are server-side: the rate limits above, cached results served free, and the officer passcode for writes.
- Deploy a zip function with `aws lambda update-function-code --function-name floodlens-<name> --zip-file fileb://<name>.zip`. `assemble-results` is built with `docker build --provenance=false` (Lambda rejects BuildKit attestation manifests) and pushed to ECR.
