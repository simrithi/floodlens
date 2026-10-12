# backend: analysis pipeline, model server and AWS workers

Python 3.12. Everything the front end shows is produced here.

| Folder | What it is |
|---|---|
| [`core/`](core/) | The analysis itself: models, segmentation, depth, geometry, road profile, terrain, hydrology, drainage, water depth, scoring |
| [`serve/`](serve/) | The SageMaker container: `/ping` and `/invocations`, one dashcam frame per call, all three models loaded once |
| [`lambdas/`](lambdas/) | The AWS workers around the endpoint, and the IAM and state-machine JSON that define them |
| [`scripts/`](scripts/) | Data fetching, map-layer and flow export, findings, validation helpers, `publish_site.sh` |
| [`validation/`](validation/) | Reference data: reported Delhi hotspots and Bengaluru underpasses |
| `run_local.py`, `run_validate.py` | Run the pipeline locally; check against reported hotspots |

## The pipeline

1. **Per frame** (on SageMaker, or locally): SegFormer-B2 segments the road, Depth Anything V2 estimates relative depth, YOLOv8m-seg finds potholes, and geometry measures kerbs and dips (`core/analyze.py`, `core/models.py`).
2. **Per stretch of about 60 m** (assemble Lambda, or locally): frames are grouped into cells, joined with the phone's road profile, bare-earth terrain (FABDEM), flow routing (pysheds) and the drain network, and a water-balance model gives standing-water depth for 2-, 5- and 10-year storms plus the drainage flow needed (`core/score.py`, `core/waterdepth.py`, `core/hydrology.py`, `core/drainage.py`).
3. **Findings** (`scripts/build_findings.py`): stretches predicted to hold 5 cm or more are grouped into spots, each with a cause, a fix, a priority and a confidence.

Relative depth from Depth Anything V2 is never treated as calibrated elevation, and AI text from Bedrock never feeds any number here.

## Run locally

```bash
uv venv backend/.venv && uv pip install -r backend/requirements.txt
python run_local.py --segments minto --limit 10      # a few frames (needs models, see scripts/download_assets.py)
python run_local.py --rescore                         # recompute risk from an existing analysis.json, no GPU
python scripts/build_findings.py --city delhi         # findings from analysed surveys
python run_validate.py                                # Delhi hotspot validation -> data/outputs/validation.json
python scripts/export_map_layers.py --city bengaluru  # hollows, drains, route profile
python scripts/export_flow.py --sequence 3827609      # flow lines for a survey
```

`data/` (footage, rasters, outputs) is git-ignored and must be present first. The official Bengaluru drains (`data/geo/bengaluru/swd_ksrsac_2022.json`) are KSRSAC's public-domain KML maps from OpenCity, converted to a list of `{type, coords}` lines.

## Publish a finished survey

```bash
bash scripts/publish_site.sh 3827609 lth bengaluru
```

Pulls every finished survey's `analysis.json`, builds flow lines and findings, copies frames and overlays to the site bucket, and invalidates CloudFront. The script header lists each step.
