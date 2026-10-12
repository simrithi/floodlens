# Changelog

All notable changes. Dates are when the change landed.

## 0.1.0 (2026-10-12) - AWS hackathon submission

### Added
- LICENSE (Apache-2.0) and NOTICE for the data licences; architecture diagrams (`docs/architecture.md`); `docs/LEARNINGS.md`.
- `npm run dev:demo`: run the app with no AWS account and no `data/` folder, reading the published results.
- A manual deploy workflow (needs the one-time setup in `infra/README.md`) and a quieter Dependabot configuration.
- Name and logo: the web app is now called Varshik everywhere users see it, with a new mark (a raindrop with a road running into it) and favicon. AWS resource names still start with `floodlens-` and are unchanged.
- AI frame check on every spot card: Bedrock Nova Lite reads the spot's dashcam frames for a visible drain inlet and blockage. Shown as evidence to verify, with a 30-per-hour limit.
- Officer brief in English (Nova Lite) and Hindi (Nova Pro). Rejected unless every number and spot id matches the findings; spot names are added by code. 20 fresh briefs per hour.
- Daily forecast alert: EventBridge Scheduler at 17:00 IST, tomorrow's rain against each spot's depth curve, an SNS email, an "Alerts" chip and a "Tomorrow" rain preset in the app.
- Officer log: approve an alert action or report what happened on the ground, stored in DynamoDB behind a passcode. `backend/scripts/compare_observations.py` compares reports with predictions.
- 4K survey of Delhi, Bengaluru ORR and Bellandur surveys processed and published; flow lines, kerb lines (Delhi) and Bengaluru official drain network (KSRSAC 2022, converted from OpenCity KML).
- `backend/scripts/publish_site.sh`: publish a finished survey to the live site in one command.
- Backend tests (23), real infrastructure tests (5), CI workflow, SECURITY and CONTRIBUTING.
- A Fail state at the end of the pipeline, so a failed run shows FAILED in Step Functions.
- Error alarms for `forecast` and `actions`, so every Lambda has one; 14-day retention on every Lambda and endpoint log group.
- `infra/deploy.sh`: build, upload and invalidate the web app in one command.
- README sections "AI used" and "Tests and verification".

### Changed
- `invoke-frame` stores each frame's record in S3 and returns a pointer, because a Map over 422 frames exceeded Step Functions' 256 KB state limit.
- `assemble-results` now has 3 GB of memory and a 15-minute timeout (it timed out at 60 s on 422 frames). `frame-check` and `officer-brief` timeouts raised to 90 s and 180 s.
- The two AI endpoints validate city, spot and language strictly and answer 400 to anything else.
- Cached frame checks, briefs and alerts are also written to the site bucket so the app can read them.
- README: new section "What the results do and do not show", with the weaker validation results stated plainly; READMEs for `infra/`, `ui/`, `backend/`, `backend/lambdas/` and `docs/`.

### Removed
- Kannada briefs: the machine translation was not good enough to offer. Kannada and other local-language printing is listed as future scope.

### Fixed
- Function URLs returned 403: the resource policy lacked `InvokeFunction` via function URL.
- A missing cache object crashed the Lambdas (S3 returned AccessDenied without `s3:ListBucket`).
- Forecast and frame check looked for fields and folders that the real findings do not have, so they skipped every spot.
- The live site served nothing under `/analysis/`: street view, findings, layers and validation were all missing.
- A Kannada brief translated "Connaught Place" as "Kanyakumari Place"; place names are no longer written by the model.

### Known issues
- The upload and run-status Function URLs return 403 and are not used by the app.
- CloudFront does not add security headers (HSTS, content security policy).
- Spot ids are renumbered when findings are rebuilt, so cached frame checks go stale.
- The nine Lambdas share one IAM role; everything except the web stack is created with the CLI, not CDK.
- Bengaluru ORR has no kerb lines.
- The Hindi brief is machine-written and has not been reviewed by a fluent reader.

## 2026-10-12
- Added the Varshik README, documentation, tables and architecture diagrams.

## 2026-10-11
- Added Step Functions pipeline orchestration and the Lambdas for frame check, brief, forecast and officer log.
- Merged the backend v2 hydrology and drainage water-depth risk model, matching the front end.
- Checkpoint: backend scaffold, Lambdas, CDK web stack, live S3 and CloudFront site.

## 2026-10-09
- Initial commit: the web app scaffold (React, TypeScript, Vite, MapLibre).
- Dark green-tinted palette; detail panel split into tabs.
