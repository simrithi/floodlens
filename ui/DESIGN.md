---
version: alpha
name: FloodLens
description: "Dark 'flood control room' dashboard. Based on the Linear design system (reference/awesome-design-md/design-md/linear.app/DESIGN.md): near-black canvas, four-step charcoal surface ladder, hairline borders, Inter type with negative tracking on display sizes. Changes for FloodLens: the single UI accent is water blue (#4c9aff) instead of Linear lavender, and a dedicated 5-step risk scale is reserved for data (map, overlays, charts) only."

colors:
  primary: "#4c9aff"
  on-primary: "#ffffff"
  primary-hover: "#7ab4ff"
  primary-focus: "#3d8af0"
  ink: "#f7f8f8"
  ink-muted: "#d0d6e0"
  ink-subtle: "#8a8f98"
  ink-tertiary: "#62666d"
  canvas: "#010102"
  surface-1: "#0f1011"
  surface-2: "#141516"
  surface-3: "#18191a"
  surface-4: "#191a1b"
  hairline: "#23252a"
  hairline-strong: "#34343a"
  hairline-tertiary: "#3e3e44"
  semantic-success: "#27a644"
  semantic-overlay: "#000000"
  risk-0: "#1d4ed8"   # safe / drains well
  risk-1: "#06b6d4"   # minor puddling
  risk-2: "#facc15"   # moderate
  risk-3: "#f97316"   # high
  risk-4: "#ef4444"   # will waterlog

typography:
  fontFamily: "Inter, SF Pro Display, -apple-system, system-ui, Segoe UI, Roboto, sans-serif"
  monoFamily: "JetBrains Mono, ui-monospace, SF Mono, Menlo, Consolas, monospace"
  display-lg: { fontSize: 56px, fontWeight: 600, lineHeight: 1.10, letterSpacing: -1.8px }
  display-md: { fontSize: 40px, fontWeight: 600, lineHeight: 1.15, letterSpacing: -1.0px }
  headline:   { fontSize: 28px, fontWeight: 600, lineHeight: 1.20, letterSpacing: -0.6px }
  card-title: { fontSize: 22px, fontWeight: 500, lineHeight: 1.25, letterSpacing: -0.4px }
  body:       { fontSize: 16px, fontWeight: 400, lineHeight: 1.50, letterSpacing: -0.05px }
  body-sm:    { fontSize: 14px, fontWeight: 400, lineHeight: 1.50, letterSpacing: 0 }
  caption:    { fontSize: 12px, fontWeight: 400, lineHeight: 1.40, letterSpacing: 0 }
  button:     { fontSize: 14px, fontWeight: 500, lineHeight: 1.20, letterSpacing: 0 }
  eyebrow:    { fontSize: 13px, fontWeight: 500, lineHeight: 1.30, letterSpacing: 0.4px }
  mono:       { fontSize: 13px, fontWeight: 400, lineHeight: 1.50, letterSpacing: 0 }

rounded: { xs: 4px, sm: 6px, md: 8px, lg: 12px, xl: 16px, pill: 9999px }
spacing: { xxs: 4px, xs: 8px, sm: 12px, md: 16px, lg: 24px, xl: 32px, xxl: 48px }
---

## Overview

FloodLens is a data product: the map and the dashcam frames are the protagonists, the chrome is a quiet dark frame around them (Linear's "product screenshot is the hero" rule, applied to a live app).

## Rules

### Colour
- `canvas` is the app background. Panels sit on `surface-1` with a 1px `hairline` border; hovered / selected items lift to `surface-2`; menus and popovers to `surface-3`.
- `primary` (water blue) is the only UI accent: brand mark, primary button, focus ring, selected state, links. Never as a panel fill.
- `risk-0 … risk-4` are **data colours only**: heatmap, road segments, frame overlays, risk badges, chart bars. Never use them for buttons or chrome.
- Risk score → colour: 0–19 risk-0, 20–39 risk-1, 40–59 risk-2, 60–79 risk-3, 80–100 risk-4.
- Water overlay on dashcam frames: `primary` at 35% opacity. Pothole outline: `risk-4`. Kerb line: `risk-2`.

### Type
- Inter everywhere; JetBrains Mono for numbers that update live (coordinates, mm/hr, scores) and IDs.
- Display sizes use negative tracking; eyebrows (panel section labels) use +0.4px tracking, uppercase is not used.
- Weights: 400 body, 500 labels/buttons, 600 headlines. No 700+.

### Shape & depth
- Buttons and inputs: `rounded.md` 8px. Panels/cards: `rounded.lg` 12px. Map and frame viewer: `rounded.xl` 16px. Status pills: `rounded.pill`.
- Depth comes from the surface ladder + hairlines, not drop shadows. Exception: floating panels over the map get a soft shadow so they separate from map tiles.
- Focus ring: 2px `primary-focus` outline at 50% opacity.

### Layout
- Desktop app shell: 56px top bar · left stats rail 280px · map (fills) · right detail panel 360px · bottom rain-simulator bar.
- Below 1024px: left rail hides behind a toggle. Below 768px: right panel becomes a bottom sheet; touch targets ≥44px.

### Motion
- Motion explains data (rain level rising, risk colours changing, counters ticking). 150–250ms ease-out for UI; no decorative animation.

## Don't
- Don't ship a light theme for now.
- Don't introduce a second UI accent; risk colours stay inside data.
- Don't use gradients or glows on chrome. Glow is allowed only on map data layers.
- Don't use pure #000 as background.
