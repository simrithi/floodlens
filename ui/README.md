# ui: the Varshik web app

React 19, TypeScript, Vite and MapLibre. It reads the pipeline's output over HTTP and renders it as a map, a spot list, street view and a printable report.

## Run

```bash
npm install
npm run dev      # http://localhost:5173, serves /analysis from ../data/outputs
npm run dev:demo # same, but reads the published results from the live site (no data/ and no AWS account)
npm run build    # type-check and production build into dist/
npm run lint     # oxlint
```

## Routes

| Route | What it shows |
|---|---|
| `/` | Landing page |
| `/map` | The dashboard: priority list, spot card, rain simulator, layers, street view, walkthrough |
| `/report/<city>` | Printable findings report (`?print=1` opens the print dialog) |

`?survey=delhi`, `?survey=blr-orr` or `?survey=blr-bellandur` opens a survey; `?tour=1` starts the walkthrough.

## Configuration (build-time)

| Variable | Purpose |
|---|---|
| `VITE_ANALYSIS_BASE` | Where the analysis files are served from (default `/analysis`) |
| `VITE_API_FRAME_CHECK` | Frame-check Function URL. Without it the "Check frames with AI" button is hidden |
| `VITE_API_BRIEF` | Officer-brief Function URL. Without it the brief tab only shows a cached brief |
| `VITE_API_ACTIONS` | Officer-log Function URL. Without it the approve and report buttons are hidden |

Set them in `.env.production` (git-ignored).

## What it reads

Under `ANALYSIS_BASE`: `findings-<city>.json`, `validation.json`, `route_profile.json`, `drains*.geojson`, `hollows*.json` and `.png`, `reported-<city>.json`, and per survey `<sequence>-<size>/` with `analysis.json`, `flow.geojson`, `kerb_lines.geojson` and the `frames/`, `overlays/` and `depth/` images. Cached AI results are read from `checks/<city>/<spot>.json`, `briefs/<city>-<lang>.json` and `alerts/<city>-<date>.json`. A missing optional file hides its layer; a missing `analysis.json` shows "No pipeline output yet".

## Where things are

| Path | Contents |
|---|---|
| `src/dashboard/` | Dashboard, spot card (`spots.tsx`), AI blocks (`aws-panels.tsx`), details, layers |
| `src/map/` | MapLibre stage and layers |
| `src/report/` | Printable report and the officer brief tab |
| `src/streetview/` | Dashcam frame viewer with the model overlays |
| `src/data/` | Loaders and types for each file above, and `aws.ts` for the Function URLs |
| `src/state.tsx` | App state: survey, rain, selection, findings, alert |
| `DESIGN.md` | Visual design notes |
