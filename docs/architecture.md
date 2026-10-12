# Architecture

Everything here is deployed in `us-east-1`. Names in quotes are real resources. See the [README](../README.md) for what each part does and the [AWS notes](AWS_SUBMISSION.md) for resources, cost and teardown.

## 1. The whole system

```mermaid
flowchart LR
    subgraph Inputs
        V["Dashcam frames<br/>and phone sensors"]
        D["Copernicus GLO-30 and FABDEM<br/>(AWS Registry of Open Data)"]
        W["Drain maps"]
    end

    V -->|"upload frames.json"| RAW[("S3 raw bucket")]
    RAW -->|"EventBridge rule"| START["start-run Lambda"]
    START --> SFN["Step Functions<br/>floodlens-pipeline"]
    SFN -->|"one frame at a time"| INV["invoke-frame Lambda"]
    INV --> SM["SageMaker endpoint<br/>SegFormer-B2, Depth Anything V2,<br/>YOLOv8m-seg (GPU)"]
    SM --> OUT[("S3 outputs bucket")]
    SFN --> ASM["assemble-results Lambda<br/>water model per 60 m stretch"]
    D --> ASM
    W --> ASM
    ASM --> OUT

    OUT -->|"publish_site.sh"| SITE[("S3 site bucket")]
    SITE --> CF["CloudFront"]
    CF --> APP["Varshik web app<br/>React, MapLibre"]

    APP -->|"Function URL"| FC["frame-check Lambda"]
    APP -->|"Function URL"| BR["officer-brief Lambda"]
    APP -->|"Function URL"| ACT["actions Lambda"]
    FC --> BED["Amazon Bedrock<br/>Nova Lite"]
    BR --> BED2["Amazon Bedrock<br/>Nova Lite, Nova Pro"]
    ACT --> DDB[("DynamoDB<br/>FloodLensActions")]
    ACT -.->|"passcode"| SSM["Parameter Store"]

    SCHED["EventBridge Scheduler<br/>17:00 IST"] --> FCST["forecast Lambda"]
    FCST -->|"tomorrow's rain"| OM["Open-Meteo"]
    FCST --> SNS["SNS email"]
    FCST --> SITE
```

## 2. One survey through the pipeline

```mermaid
sequenceDiagram
    participant U as Upload
    participant EB as EventBridge
    participant SR as start-run
    participant SF as Step Functions
    participant IF as invoke-frame
    participant SM as SageMaker endpoint
    participant S3 as S3 outputs
    participant AS as assemble-results
    participant DB as DynamoDB runs

    U->>EB: frames.json lands in the raw bucket
    EB->>SR: start
    SR->>DB: create the run row
    SR->>SF: start execution
    loop every frame, one at a time
        SF->>IF: frame
        IF->>SM: image location and metadata
        SM->>S3: overlay and depth images
        SM-->>IF: frame record
        IF->>S3: save the full record
        IF-->>SF: small pointer only
    end
    SF->>AS: all pointers
    AS->>S3: read the records back
    AS->>S3: write analysis.json (stretches, depth, drainage)
    AS->>DB: status done
```

A Map state cannot carry hundreds of full records: Step Functions limits a state to 256 KB. That is why each record goes to S3 and only a pointer travels through the state machine.

## 3. Failure handling

```mermaid
flowchart TD
    M["Map: analyse every frame"] --> A["Assemble"]
    A --> OK(["analysis.json written"])
    M -->|"any error"| MF["MarkFailed:<br/>record status failed"]
    A -->|"any error"| MF
    MF --> RF(["RunFailed (Fail state):<br/>Step Functions shows FAILED"])
```

Earlier versions ended `MarkFailed` normally, so a failed run showed SUCCEEDED. The only reliable success signal is still the output file `<sequence>-<size>/analysis.json`.

## 4. The AI features and their guardrails

```mermaid
flowchart TD
    subgraph Check["Frame check (Nova Lite)"]
        C1["Spot id from the app"] --> C2{"Valid city and spot id?"}
        C2 -->|"no"| E1["400, nothing read"]
        C2 -->|"yes"| C3{"Cached?"}
        C3 -->|"yes"| R1["Return the cached answer"]
        C3 -->|"no"| C4{"Under 30 fresh checks this hour?"}
        C4 -->|"no"| E2["429"]
        C4 -->|"yes"| C5["Best frame plus up to 3 more<br/>sent to Nova Lite"]
        C5 --> C6{"Valid JSON in the fixed schema?<br/>one retry"}
        C6 -->|"yes"| C7["Cache and return:<br/>evidence to verify on site,<br/>never an input to any number"]
        C6 -->|"no"| E3["Error, no guess"]
    end

    subgraph Brief["Officer brief (Nova Lite, Nova Pro)"]
        B1["Findings: spots only,<br/>no methods text"] --> B2["Model writes the brief.<br/>Spots are named only by id"]
        B2 --> B3{"Every number is in the findings<br/>and every spot id is present?<br/>up to 3 attempts"}
        B3 -->|"yes"| B4["Code adds the legend with the exact<br/>place names, then caches by findings hash"]
        B3 -->|"no"| E4["Rejected, never shown"]
    end
```

## 5. Publishing a finished survey

```mermaid
flowchart LR
    A["analysis.json in the<br/>outputs bucket"] --> P["publish_site.sh"]
    P --> F["flow lines, findings<br/>(built locally)"]
    P --> I["frames, overlays, depth maps<br/>(copied inside AWS)"]
    F --> S[("site bucket<br/>/analysis")]
    I --> S
    S --> X["CloudFront cache invalidation"]
    X --> L(["live on the site"])
```

The web app itself is published separately with `infra/deploy.sh` (or the manual **deploy** workflow).
