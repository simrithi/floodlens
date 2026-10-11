# Varshik
### Geospatial intelligence for identifying urban waterlogging hotspots

Varshik is a geospatial decision-support system designed to help identify road locations that may be vulnerable to urban waterlogging. It brings together road-level visual evidence, phone-sensor observations, terrain elevation, drainage infrastructure, and analytical outputs in a map-based interface for Delhi and Bengaluru.

The engineering challenge is not simply to plot potential flood locations. It is to connect heterogeneous datasets while preserving the distinction between observed evidence, mapped infrastructure, model-derived estimates, AI-generated interpretations, and conditions that still require field verification.

> **Project status:** Varshik combines a Python-based geospatial analytical pipeline, a React/TypeScript mapping interface, and AWS-backed delivery and event-driven capabilities. The AI-assisted inspection, multilingual briefing, rainfall-analysis, notification, and field-observation workflows described below are implemented. Their outputs remain decision-support signals and must not be treated as authoritative flood warnings or substitutes for verified field conditions.

## Contents

- [What Varshik does](#what-varshik-does)
- [System overview](#system-overview)
- [Architecture](#architecture)
- [Data and analytical pipeline](#data-and-analytical-pipeline)
- [Frontend](#frontend)
- [AWS architecture](#aws-architecture)
- [Amazon SageMaker inference and terrain analysis](#amazon-sagemaker-inference-and-terrain-analysis)
- [AI and event-driven capabilities](#ai-and-event-driven-capabilities)
- [Data contracts and output layout](#data-contracts-and-output-layout)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Security and operational controls](#security-and-operational-controls)
- [Data provenance and licensing](#data-provenance-and-licensing)
- [Limitations](#limitations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

## What Varshik does

Varshik combines several sources of evidence to help surface locations that may warrant closer investigation.

- **Road-level visual evidence:** dashcam frames provide context about road geometry, underpasses, kerbs, visible drainage inlets, standing water, and other visible conditions.
- **Sensor observations:** phone-sensor data contributes route-specific context, subject to the sensors available and their measurement quality.
- **Terrain elevation:** a bare-earth elevation model helps identify broad depressions and terrain patterns that may influence surface-water movement.
- **Drainage infrastructure:** official drainage maps provide spatial context for mapped drainage networks and nearby infrastructure.
- **Analytical outputs:** the pipeline produces findings, depth-related artefacts, flow features, kerb geometries, and other outputs that can be inspected in the application.

The application focuses on **Delhi and Bengaluru**. It presents analysis through city reports and an interactive map so that a user can examine a location in its geographic context rather than relying on an isolated score or number.

### What Varshik is not

Varshik should not be treated as a real-time flood-warning authority or a replacement for hydraulic modelling, field inspections, or official emergency procedures. A mapped hotspot is not proof that flooding is occurring. A model-derived depth is an estimate, not a direct measurement, unless independently verified.

## System overview

![Varshik end-to-end system architecture](docs/diagrams/Varshik_System_Architecture.svg)

*Figure 1. End-to-end architecture connecting geospatial inputs, analysis outputs, the web application, and AWS services.*

The pipeline and frontend have separate responsibilities:

1. The **Python pipeline** processes survey and geospatial inputs and writes analysis artefacts.
2. The **output layer** exposes structured JSON, GeoJSON, images, and depth-related files.
3. The **frontend** requests the required artefacts over HTTP and renders them as maps, reports, and visual evidence.
4. The **cloud delivery layer**, serves the built frontend and approved analysis artefacts through Amazon S3 and Amazon CloudFront.
5. The serverless capabilities operate alongside the analytical pipeline while preserving the boundary between model estimates and verified observations. Amazon SageMaker provides a real-time inference endpoint for the project's deployed model and supports the model-inference workflow used alongside geospatial and terrain analysis.

## Architecture

### 1. Analytical backend

The backend uses **Python 3.12** and a project-local environment managed with `uv`. It processes the project's survey data and produces sequence-level and city-level outputs.

Processing artefacts are kept separate from the frontend. This lets the UI request the results needed for a given view without rerunning the entire analytical workflow whenever a user opens a map or changes a report.

### 2. Data interface

The frontend reads pipeline outputs through an HTTP base path controlled by `VITE_ANALYSIS_BASE`. The documented default is `/analysis`.

This abstraction separates the logical path used by the frontend from the physical location of the files. In development, a local Vite setup can expose the outputs; in a production deployment, the same paths can be served from object storage through a CDN.

### 3. Frontend application

The web application uses:

- **React 19** for component-based UI.
- **TypeScript** for static type checking and explicit data contracts.
- **Vite 8** for development and build tooling.
- **MapLibre** for map rendering and geospatial interaction.

The principal route patterns are:

- `/` — application entry point.
- `/map` — interactive map.
- `/report/<city>` — city-specific report.

TypeScript can catch many implementation errors during development, but it does not validate arbitrary JSON received at runtime. External analysis files should still be checked for missing or malformed fields where appropriate.

## Data and analytical pipeline

### Geospatial inputs

Varshik combines inputs that describe different aspects of the environment. They should not be treated as interchangeable:

| Input | What it contributes | Important limitation |
|---|---|---|
| Dashcam frames | Visual context for road-level conditions | Visibility depends on camera angle, lighting, occlusion, and survey timing |
| Phone-sensor observations | Context associated with a surveyed route | Reliability depends on sensor availability, calibration, and recording quality |
| Bare-earth elevation | Broad terrain gradients and potential low points | Coarse resolution cannot represent every kerb, road crown, or narrow channel |
| Official drainage maps | Mapped drainage infrastructure | May omit undocumented, modified, blocked, or outdated infrastructure |
| Pipeline outputs | Derived findings and depth/flow-related artefacts | Accuracy depends on input quality and the assumptions of the underlying analysis |

### Elevation data and AWS Registry of Open Data

The project uses the **AWS Registry of Open Data** as a source for the **Copernicus GLO-30 Digital Elevation Model** relevant to terrain analysis. The dataset has approximately 30-metre spatial resolution and can help identify broad topographic patterns.

The Registry of Open Data is a data-access resource; it does not itself perform Varshik's terrain analysis. The elevation model is an input to the project's workflow, not a complete flood simulation.

At this resolution, terrain data may not capture street-scale features that govern urban drainage. Results should therefore be interpreted alongside road geometry, drainage information, visual evidence, and the assumptions of the analytical model. Where precise street-level hydraulic behaviour is required, higher-resolution survey data may be necessary.

### Why JSON and GeoJSON

Varshik produces structured artefacts rather than requiring the browser to understand the internals of the Python pipeline.

- **JSON** represents hierarchical findings, metadata, and numerical outputs.
- **GeoJSON** represents spatial features such as points and lines with associated properties.
- **Image artefacts** provide frames, overlays, and depth visualisations for inspection.

This creates a boundary between analysis and presentation. It also means output schemas need to remain consistent, and clients should handle missing data and unsupported geometries safely.

![Varshik data pipeline and application delivery](docs/diagrams/Varshik_Data_Pipeline.svg)

*Figure 2. Source data is processed into structured outputs, which are delivered to the React and MapLibre application.*

## Frontend

The interface uses MapLibre to place findings and spatial features in geographic context. This matters because a location's relationship to nearby roads, drainage features, and terrain can be more informative than a standalone numerical value.

The data base path is configured with:

```text
VITE_ANALYSIS_BASE=/analysis
```

If this variable is not supplied, the application uses `/analysis` as its default.

The frontend build and analysis artefacts are deployed with an explicit path convention. Validate the application through its delivery URL as well as checking the underlying storage objects.

## AWS architecture

The AWS architecture delivers the application and its analytical artefacts securely and runs event-driven extensions for visual evidence inspection, multilingual briefs, rainfall analysis, notifications, and field observations.

### AWS service map

| Service or technology | Responsibility | Status |
|---|---|---|
| AWS Registry of Open Data | Access to public geospatial input data, including Copernicus GLO-30 DEM | Used as a data source in the project workflow |
| Amazon S3 | Store built frontend assets and approved analysis artefacts | Implemented delivery layer |
| Amazon CloudFront | HTTPS content delivery for frontend and analysis requests | Implemented delivery layer |
| AWS CDK v2 with TypeScript | Define and review infrastructure as code | Implemented as infrastructure as code in the infrastructure directory |
| AWS Lambda | Serverless execution for visual checks, forecast analysis, and field-action APIs | Implemented |
| Amazon Bedrock | Vision-based frame inspection and grounded officer briefs | Implemented |
| Amazon SageMaker | Hosts the deployed model behind a real-time inference endpoint used for model predictions supporting geospatial and terrain analysis | Implemented |
| Amazon EventBridge Scheduler | Invoke the rainfall-analysis workflow on a schedule | Implemented |
| Amazon SNS | Send forecast notifications | Implemented |
| Amazon DynamoDB | Store officer actions and field observations | Implemented |
| Amazon CloudWatch | Logs, metrics, alarms, and operational visibility | Implemented for configured workloads |

### Amazon S3: object storage

The deployment places the built frontend at the root of a private S3 bucket and the application's analysis artefacts under the `analysis/` prefix.

S3 is an object store. Keys may look like directories, but they are not conventional filesystem directories. The application should rely on stable object-key conventions rather than filesystem assumptions.

The bucket controls include:

- S3 Block Public Access.
- Server-side encryption.
- A bucket policy that grants the required access to CloudFront.
- A clear separation between frontend assets and analysis objects.
- Uploading only the files needed by the application.

Raw input data should not be uploaded automatically simply because it exists in the development repository. The deployment must respect source-data licensing and project-specific exclusions.

### Amazon CloudFront and Origin Access Control

The CloudFront distribution serves the frontend and analysis artefacts over HTTPS while using **Origin Access Control (OAC)** to access the private S3 origin. The bucket does not need to be publicly readable.

The delivery configuration enables HTTP/2 and HTTP/3, compression, and a price class that covers India.

#### Single-page application routing

Client-side routes such as `/map` and `/report/bengaluru` may reach CloudFront as direct URL requests. Without a rewrite, S3 may look for an object with that literal key and return an error.

The implemented solution is a CloudFront Function on the viewer-request event that rewrites eligible extensionless application routes to `/index.html`.

This rewrite must be selective. It must not turn every missing JSON, GeoJSON, image, or analysis object into `index.html`, because doing so would hide missing-data errors and make debugging difficult.

#### Cache policy

Different objects have different freshness requirements. The implemented configuration uses separate caching behaviour:

| Content type | Implemented cache behaviour | Reason |
|---|---|---|
| `index.html` | No-cache / revalidation | Users should receive the current application entry point |
| Hashed frontend assets | One year, immutable | Content-addressed filenames change when the asset changes |
| JSON and GeoJSON analysis | Five minutes | Balances delivery efficiency with update visibility |
| Analysis images | One day | Reduces repeated image delivery while allowing periodic refresh |

GeoJSON should be served with the `application/geo+json` content type. JSON should use an appropriate JSON content type.

These cache settings should be checked against the deployed distribution when changing delivery behaviour.

### AWS CDK and infrastructure as code

AWS CDK v2 infrastructure is maintained in an `infra/` directory and uses TypeScript. CDK describes resources in code and synthesises them into AWS CloudFormation templates.

The infrastructure design follows these principles:

- **Reproducibility:** infrastructure is defined in source rather than created only through manual console steps.
- **Reviewability:** resource and permission changes can be inspected before deployment.
- **Least privilege:** roles and policies grant only the permissions required for each task.
- **Traceability:** resources should carry the `Project=Varshik` tag where supported.
- **Cost awareness:** potentially expensive or public resources should be deliberately approved before creation.

The default region for regional resources is `ap-south-1` (Mumbai). CloudFront is global. If a custom domain is configured for CloudFront, its ACM certificate must be provisioned in `us-east-1`.

## Amazon SageMaker inference and terrain analysis

Varshik uses **Amazon SageMaker** for model inference through a deployed **real-time endpoint**. This is a distinct part of the architecture from Amazon Bedrock: SageMaker serves the project's deployed predictive model, while Bedrock is used for foundation-model tasks such as visual evidence descriptions and grounded multilingual briefs.

The SageMaker workflow supports inference associated with Varshik's geospatial and terrain-analysis process. The analytical pipeline prepares the relevant inputs, sends an inference request to the deployed endpoint, and uses the returned prediction as one input to the wider decision-support workflow. The result should remain traceable to its input features and model version where those details are available.

### Inference flow

1. **Prepare inputs:** the analysis workflow assembles the geospatial or terrain-derived features expected by the deployed model.
2. **Invoke the endpoint:** the application or backend calls the SageMaker real-time endpoint using authorised AWS credentials and the expected request schema.
3. **Validate the response:** check that the response is well-formed, contains the expected fields, and has valid numeric values before using it downstream.
4. **Integrate the prediction:** combine the model output with the other relevant spatial findings and evidence; do not treat the prediction as a verified field measurement.
5. **Monitor and evaluate:** track endpoint errors, latency, throttling, model version, and prediction quality against reliable field observations where available.

| SageMaker component | Role in Varshik | Engineering consideration |
|---|---|---|
| Deployed model | Produces predictions from the features supplied by the geospatial/terrain workflow | Document the model type, feature schema, and version used in the actual deployment. |
| Real-time inference endpoint | Serves online inference requests | Endpoint availability, latency, invocation permissions, and cost depend on the deployed configuration. |
| Request/response contract | Defines how the backend sends features and consumes predictions | Validate inputs and outputs; handle timeouts, errors, and unexpected responses explicitly. |
| Prediction integration | Makes model outputs available to the wider analysis and mapping workflow | Label predictions as model-derived estimates and retain their provenance. |

The exact model algorithm, endpoint name, instance type, feature list, and prediction fields are intentionally not specified here because they should match the deployed SageMaker configuration rather than be guessed in documentation.

## AI and event-driven capabilities

The following implemented workflows connect image-based evidence review, grounded reporting, scheduled rainfall analysis, notifications, and field feedback. The safeguards described here are part of the intended runtime behaviour; deployment-specific values should remain aligned with the active AWS configuration.

![Varshik AI and event-driven workflows](docs/diagrams/Varshik_AI_Event_Workflows.svg)

*Figure 3. Event-driven workflows for visual inspection, rainfall analysis, notifications, and field observations.*

### 1. Amazon Bedrock for visual evidence inspection

The frame-check workflow uses a Python 3.12 Lambda function to accept a city and spot identifier, retrieve the relevant findings and original dashcam frames from S3, and invoke a vision-capable Amazon Bedrock model through the Converse API. This is separate from the SageMaker real-time endpoint used for the project's predictive model inference.

The model's scope is intentionally narrow: describe visible evidence rather than independently determine flood depth or replace the hydrological analysis.

The structured response includes fields for:

- Whether the location appears to be an underpass.
- Whether a drainage inlet is visible.
- The apparent inlet condition.
- Visible blockage categories, such as garbage, silt, vegetation, or a parked vehicle.
- Whether standing water or water staining is visible.
- Whether kerb openings are visible.
- Notes and the frame identifiers used.

The model returns `unclear` when the image does not support a confident conclusion. An inlet outside the camera's field of view must not automatically be labelled blocked.

#### Validation and caching

The implementation validates the model response against a defined JSON schema. Invalid output triggers one controlled retry; if validation still fails, the endpoint returns an explicit error rather than passing malformed data to the UI.

Results are cached in S3 under:

```text
analysis/checks/<city>/<spotId>.json
```

The cache record includes the model identifier and timestamp. The workflow enforces a limit of 30 calls per hour. The shared DynamoDB-backed rate limiter applies the limit across Lambda execution environments, rather than relying on a process-local counter.

| Cache field / control | Purpose |
|---|---|
| City and spot ID | Identifies the cached inspection result. |
| Model identifier | Makes the generating model traceable. |
| Timestamp | Records when the result was produced. |
| Shared DynamoDB rate limiter | Enforces the hourly request limit across Lambda execution environments. |
| Schema validation and one retry | Prevents malformed model output from being passed to the UI. |

AI output is an interpretation of images, not a confirmed field inspection. The interface labels it accordingly and retains the ability for an engineer to verify the location on site.

### 2. Grounded, multilingual officer briefs

The Bedrock briefing workflow generates a one-page city brief in English, Kannada, or Hindi from the structured findings JSON.

The model is instructed to summarise the locations of concern, explain the causes stated in the source findings, and preserve spot identifiers and units. It must not invent numerical values absent from the input.

Post-generation validation extracts numbers from the output and checks them against the source data, accounting for common formatting differences and Kannada or Devanagari digits. If unsupported numbers are found, the function retries once and then fails closed if the result remains invalid.

Numerical presence alone does not guarantee correctness: a value can still be associated with the wrong location or unit. The brief should preserve the relationships between values, identifiers, units, and source records. Kannada and Hindi output should receive human review before operational use.

Generated briefs are cached by city and language with the model identifier, timestamp, and input hash, so changes to source findings can invalidate stale output.

### 3. Scheduled rainfall analysis

The forecasting workflow uses Amazon EventBridge Scheduler to invoke a Lambda function daily at **17:00 India Standard Time**.

The function retrieves city findings and spot coordinates, queries the Open-Meteo hourly precipitation forecast, and compares forecast rainfall with existing water-depth-versus-rainfall curves.

A critical modelling constraint is the difference between hourly precipitation and a short-duration design storm. Hourly rainfall must not be silently treated as a 15-minute burst. The project specification calls for a sourced, city-specific conversion ratio when one is available. Otherwise, the output must explicitly say that hourly rain is used and the short-duration burst is not modelled.

For rainfall values between known curve points, linear interpolation can be used:

\[
d(r)=d_1+\frac{r-r_1}{r_2-r_1}(d_2-d_1)
\]

Here, \(r\) is rainfall intensity and \(d\) is estimated depth. This is an interpolation method, not proof that the hydrological relationship is linear under all conditions. Out-of-range values, missing points, and unsupported extrapolation require explicit handling.

The implemented advisory thresholds are:

- **15 cm or more** at an underpass or low-lying sag: consider closing the location.
- **5 cm to below 15 cm:** clear inlets and monitor the location.

These are project-defined decision-support rules, not universal flood-safety standards. They must not independently trigger road closures or replace official emergency procedures.

| Estimated depth / data condition | Project advisory | Qualification |
|---|---|---|
| 15 cm or more at an underpass or low-lying sag | Consider closing the location | Project-defined advisory; verify with responsible authorities and field conditions. |
| 5 cm to below 15 cm | Clear inlets and monitor the location | Not a universal flood-safety standard. |
| Missing or out-of-range curve data | Report uncertainty; avoid unsupported extrapolation | Do not invent estimates unsupported by input data. |
| Hourly rainfall without a validated conversion ratio | Explicitly disclose that hourly rain is used and short-duration burst rainfall is not modelled | Do not silently treat hourly precipitation as a 15-minute burst. |

### 4. Amazon SNS notifications

The workflow publishes a consolidated daily city summary to Amazon SNS when at least one location meets the specified threshold. The workflow emits a consolidated message per city per day to reduce alert fatigue.

The summary includes affected spot identifiers, forecast information, suggested actions, and a link to the map. Email recipients must confirm their SNS subscription.

Because scheduled jobs can be retried, duplicate suppression needs explicit state management. A retry must not automatically result in another notification for the same city and date.

### 5. DynamoDB for officer actions and field observations

The DynamoDB table is named `VarshikActions`. Its key design is:

- Partition key: `city#spotId`
- Sort key: `timestamp#kind`

The table records approval or decline decisions and field observations such as whether flooding occurred, an optional reported depth, an observation date, and an optional photo reference.

The implementation accounts for timestamp precision and unique event identifiers. Secondary indexes should be added only when required by verified query patterns.

The API uses Lambda and a Function URL, with strict input validation and an officer secret stored in AWS Secrets Manager or Systems Manager Parameter Store as a SecureString. Secrets must never be embedded in frontend code or printed in logs.

The current shared-secret approach is a constrained prototype control, not a substitute for individual identity, fine-grained authorisation, or per-user auditability. A production operational deployment should use an appropriate identity system.

Field observations can be compared with model outputs using metrics such as flood-detection hit rate and depth error. Those metrics are meaningful only when the ground-truth observations are sufficiently reliable and representative.

## Data contracts and output layout

The output structure includes sequence-level folders and city-level files. Names and availability depend on the pipeline run and the data being analysed.

```text
data/
└── outputs/
    ├── <sequence>-<size>/
    │   ├── analysis.json
    │   ├── frames/
    │   ├── overlays/
    │   ├── depth/
    │   ├── flow.geojson
    │   └── kerb_lines.geojson
    ├── findings-<city>.json
    ├── drains*.geojson
    ├── hollows*.png
    ├── hollows*.json
    ├── reported-bengaluru.json
    ├── validation.json
    └── route_profile.json
```

### Important output artefacts

| Artefact | Purpose |
|---|---|
| `analysis.json` | Sequence-level analysis results |
| `frames/` | Survey images used by the application |
| `overlays/` | Visual artefacts generated by the analytical workflow |
| `depth/` | Depth-related outputs |
| `flow.geojson` | Spatial flow features |
| `kerb_lines.geojson` | Kerb-related geometries |
| `findings-<city>.json` | City-level findings |
| `drains*.geojson` | Drainage-related spatial data |
| `hollows*.png` / `hollows*.json` | Hollow/depression-related artefacts |
| `reported-bengaluru.json` | Reported Bengaluru data |
| `validation.json` | Validation output |
| `route_profile.json` | Route profile data |

Consumers should treat these files as external data: validate expected fields, handle missing objects, and avoid assuming that every sequence has every optional artefact.

## Local development

### Prerequisites

- Python 3.12
- `uv`
- Node.js compatible with the repository's Vite toolchain
- The project repository and its required input data

### Backend environment

The backend uses a `uv`-managed environment at `backend/.venv`. Create the environment with:

```bash
uv venv backend/.venv
```

Install backend dependencies using the repository manifest, then run the analysis command documented for the dataset you intend to process.

### Frontend

The UI is a Vite application built with React and TypeScript. Install dependencies using the repository's package manager and follow its existing development/build scripts. Configure `VITE_ANALYSIS_BASE` to point at the HTTP location from which the generated analysis artefacts are served.

> **Reproducibility note:** Use the exact backend and frontend scripts in the checked-in manifests. This README avoids inventing commands that may not match the current repository.

### Verify the application

After the backend outputs and frontend are available, check the following:

- `/` loads the application.
- `/map` loads the map view.
- `/report/bengaluru` and `/report/delhi` load their city reports.
- The browser can retrieve the expected JSON and GeoJSON analysis resources.
- Frames and overlays load for sequences that contain them.
- Switching surveys does not leave stale data on the map.
- Export/report actions work where implemented.
- Missing analysis objects produce visible, diagnosable errors rather than silently returning the application shell.

## Configuration

| Variable or setting | Purpose |
|---|---|
| `VITE_ANALYSIS_BASE` | HTTP base path for analysis artefacts; defaults to `/analysis` |
| AWS region | `ap-south-1` is the documented default for regional AWS resources |
| `Project=Varshik` | Resource tag specified for supported AWS resources |
| `analysis/checks/<city>/<spotId>.json` | S3 key pattern for cached frame-inspection results |
| `VarshikActions` | DynamoDB table for officer decisions and field observations |
| `city#spotId` | DynamoDB partition-key format |
| `timestamp#kind` | DynamoDB sort-key format |

Do not put credentials, secret values, or privileged access tokens in frontend environment variables. Anything bundled into a client-side application can be inspected by users.

If a custom domain is added to CloudFront, use a certificate in `us-east-1` and complete DNS validation. A custom domain is optional and should only be configured when the domain is available and authorised for use.

## Security and operational controls

Cloud resources use explicit trust boundaries. The controls below describe the implementation and operational posture; confirm exact values against the deployed AWS account before changing or auditing the environment.

### Storage and delivery

- Keep the S3 origin private and use CloudFront OAC.
- Enable S3 Block Public Access and server-side encryption.
- Upload only approved frontend assets and analysis outputs.
- Preserve source-data attribution and licensing requirements.
- Use content-specific caching and verify the behaviour of missing objects.

### IAM and serverless APIs

- Grant each Lambda function only the permissions required for its responsibility.
- Scope S3 permissions to the required prefixes where possible.
- Restrict model invocation to the intended Bedrock model.
- Validate request bodies, identifiers, and allowed values.
- Apply authentication and server-side rate limiting to public endpoints.
- Treat CORS as a browser policy, not as authentication.
- Never log credentials or sensitive payloads.

### Monitoring and budget controls

The configured operational targets include:

- CloudWatch log retention of 14 days for Lambda functions.
- Alarms for Lambda errors and Bedrock throttling.
- An AWS Budget threshold of $25 per month with alerts at 50%, 80%, and 100%.

AWS Budgets alerts do not automatically stop all resource usage. Caching, throttling, usage monitoring, and teardown procedures are still necessary.

Before enabling Bedrock, scheduled workflows, or other usage-based services, confirm permissions, quotas, expected request volume, and estimated costs. Do not provision potentially expensive resources without explicit approval.

## Data provenance and licensing

Varshik combines source footage, elevation data, drainage geometries, analytical outputs, and generated visualisations. Each category has its own provenance and limitations.

The KartaView frames used by the project are licensed under **CC BY-SA 4.0**, and required attribution must remain visible in the application. Raw footage under `data/kartaview/` and raster inputs under `data/geo/` are excluded from public deployment unless redistribution rights and an explicit data-handling review permit otherwise.

A deployment should include only the assets required by the application and should preserve applicable licence and attribution requirements. The existence of a file in a development repository does not automatically grant permission to redistribute it.

## Limitations

### Terrain resolution

A roughly 30-metre elevation model supports broad terrain analysis but may not represent street-scale drainage features. More detailed elevation data may be required for precise hydraulic modelling.

### Incomplete infrastructure records

Drainage maps can be outdated or incomplete. A mapped drain does not establish that it exists in the field, is unobstructed, or has sufficient capacity.

### Visual ambiguity

Dashcam images can be affected by occlusion, lighting, motion blur, camera position, and survey timing. A visible inlet does not prove hydraulic functionality; an image without standing water does not prove a road is flood-safe.

### Model and forecast uncertainty

Depth estimates depend on the analytical model and its assumptions. Hourly rainfall forecasts cannot automatically be treated as short-duration design storms. Interpolation outside the supported range can be misleading.

### AI reliability

Vision and language models can produce incorrect interpretations. Schema checks, constrained prompts, numerical validation, and caching reduce certain failure modes but do not guarantee factual correctness. AI-generated outputs require appropriate human review.

### Ground truth

Reliable evaluation requires verified field observations across representative locations and rainfall events. Missing reports must not be treated as proof that flooding did not occur.

## Roadmap

The core delivery and event-driven workflows described in this README are implemented. Further work should focus on improving reliability, validation, and operational readiness:

1. **Hydrological validation:** compare estimated depth and hotspot rankings with verified observations across more locations and rainfall events.
2. **Higher-resolution terrain:** evaluate finer elevation data and road-level surveys where available.
3. **Identity and auditability:** replace shared-secret access with individual identities and role-based authorisation for operational use.
4. **Forecast calibration:** validate city-specific rainfall conversions and depth curves against reliable historical or field data.
5. **Observability:** refine dashboards, alarms, structured logs, and end-to-end service health checks.
6. **AI/ML evaluation:** maintain a reviewed image set for Bedrock-assisted inspection; evaluate SageMaker prediction quality against reliable field observations; track model versions, latency, uncertainty, and failure cases.
7. **Resilience and cost controls:** test retries, duplicate suppression, rate limits, cache invalidation, and budget alerts under failure conditions.

## Contributing

Contributions should preserve the separation between data acquisition, analytical processing, structured outputs, and frontend presentation.

Before proposing a change:

1. Identify the affected output schema or interface.
2. Explain how the change handles missing or invalid data.
3. Preserve data provenance and licence requirements.
4. Avoid introducing public endpoints or cost-bearing cloud resources without review.
5. Distinguish measured values from model-derived estimates and generated interpretations.
6. Include reproducible validation steps for the affected workflow.

## Acknowledgements and project context

Varshik explores the intersection of geospatial analysis, cloud architecture, and AI-assisted decision support for urban infrastructure. The AWS implementation uses the AWS Registry of Open Data and Copernicus GLO-30 DEM as part of the geospatial workflow and connects the application delivery layer with serverless evidence inspection, forecasting, notifications, and field feedback.

The project work was undertaken with an emphasis on explaining why each service belongs in the architecture, what responsibility it owns, and what controls are needed to use it responsibly.

---

**Operational note:** Keep deployment identifiers, endpoints, model IDs, resource names, and setup commands aligned with the actual repository and AWS environment. Do not publish secret values, and verify service behaviour after infrastructure or model changes.
