// Types and helpers for the backend pipeline output (backend/core/pipeline.py -> analysis.json).
// Real measurements from dashcam frames, unlike the sample data in hotspots.ts.

import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import { distance } from './geo'

export type Run = 'lth' | 'full'

export const RUNS: { id: Run; label: string }[] = [
  { id: 'lth', label: '1280p' },
  { id: 'full', label: '4K' },
]

export const ANALYSIS_BASE: string = import.meta.env.VITE_ANALYSIS_BASE ?? '/analysis'

export type FrameRecord = {
  index: number
  segment: string
  lat: number
  lng: number
  heading: number | null
  shotDate: string
  image: string
  overlay: string
  depth: string
  roadFraction: number
  ground: { horizonY: number; inliers: number; residualStd: number } | null
  potholes: { confidence: number; bbox: number[]; depthCm: number; areaM2: number; lat: number | null; lng: number | null }[]
  dips: { depthCm: number; areaM2: number; distanceM: number; lat: number | null; lng: number | null }[]
  /** Carriageway edges seen in this frame (one per side at most). Height is not reliable and not shown. */
  kerbs: { side: 'left' | 'right'; beyond: string; dropCm: number | null; ground: [number, number][] }[]
  demElevationM: number
  /** Depth (m) of the road sag this frame sits in, from the phone-sensor profile; null without a sensor log. */
  sagM?: number | null
}

export type Factors = { terrain: number; sag?: number; surface: number; potholes: number; drainage: number; rain: number }

export type WaterPrediction = {
  station: string
  drainCapacityMmHr: number
  catchmentM2: number
  poolM2: number
  inHollow: boolean
  hollowDepthCm: number
  designStorms: { returnPeriodYears: number; rainMmHr: number; depthCm: number }[]
  curve: { rainMmHr: number[]; depthCm: number[] }
}

export type CellRecord = {
  id: string
  segment: string
  lat: number
  lng: number
  startM: number
  frameIndexes: number[]
  potholes: number
  potholeAreaM2: number
  maxDipCm: number
  dipAreaM2: number
  kerbDropCm: number | null
  kerbFrames: number
  demElevationM: number
  demRelativeM: number
  dem: 'bare' | 'surface'
  hollowDepthCm: number
  /** Low point in the road measured by the phone's sensors (underpasses); null if none or no sensor log. */
  roadSag?: { depthM: number; lengthM: number } | null
  /** This stretch is a ramp: its runoff runs down into the phone-measured sag of another stretch. */
  drainsTo?: { id: string; distanceM: number; ahead: boolean; depth2yCm: number; sagM: number } | null
  catchmentM2: number
  drain: { distanceM: number; class: string; name: string; covered: boolean }
  water: WaterPrediction
  depth2yCm: number
  factors: Factors
  risk: number
}

export type Analysis = {
  version: number
  generatedAt: string
  /** Missing in outputs written before multi-city support (Delhi). */
  city?: { key: string; name: string; drains: string }
  sequence: {
    id: number
    source: string
    url: string
    license: string
    attribution: string
    segments: { name: string; from: number; to: number; label: string }[]
  }
  input: { size: Run; workShape: [number, number]; device: string }
  rainfall: { maxHourlyMm: number; p99WetHourMm: number; note: string }
  designStorms?: { source: string; stations: { name: string; intensityMmHr: Record<string, number> }[] }
  summary: {
    frames: number
    dips: number
    potholes: number
    kerbMeasurements: number
    cells: number
    worstCells: string[]
  }
  cells: CellRecord[]
  frames: FrameRecord[]
}

/** Plain sentence for a ramp stretch, e.g. "Ramp into a low point 240 m ahead, about 20 cm expected there". */
export function rampText(d: NonNullable<CellRecord['drainsTo']>) {
  return `Ramp into a low point ${d.distanceM} m ${d.ahead ? 'ahead' : 'back'}, about ${Math.round(d.depth2yCm)} cm expected there`
}

/** A low-risk stretch that drains into a nearby low point is labelled as its ramp, not "Drains well". */
export function isRamp(cell: CellRecord) {
  return !!cell.drainsTo && cell.risk < cell.drainsTo.depth2yCm * (100 / 30)
}

export const FACTOR_LABELS: Record<keyof Factors, string> = {
  terrain: 'Hollow in bare earth',
  sag: 'Sag in the road (phone sensors)',
  surface: 'Road dips (dashcam)',
  potholes: 'Potholes',
  drainage: 'Far from a drain',
  rain: 'Storm above drain capacity',
}

/** Predicted standing water (cm) at a rain rate, interpolated on the pipeline's depth curve. */
export function depthAt(w: WaterPrediction, rainMmHr: number) {
  const xs = w.curve.rainMmHr
  const ys = w.curve.depthCm
  if (rainMmHr <= xs[0]) return ys[0]
  for (let i = 1; i < xs.length; i++) {
    if (rainMmHr <= xs[i]) {
      const t = (rainMmHr - xs[i - 1]) / (xs[i] - xs[i - 1])
      return ys[i - 1] + (ys[i] - ys[i - 1]) * t
    }
  }
  return ys[ys.length - 1]
}

/** URL of a file in a pipeline output folder (data/outputs/<sequence>-<size>/). */
export function runUrl(sequence: number, run: Run, file = '') {
  return `${ANALYSIS_BASE}/${sequence}-${run}/${file}`
}

/** URL of a file next to a loaded analysis.json (frames, overlays, kerb lines). */
export function fileUrl(a: Analysis, file = '') {
  return runUrl(a.sequence.id, a.input.size, file)
}

export async function loadAnalysis(sequence: number, run: Run, signal?: AbortSignal): Promise<Analysis> {
  const res = await fetch(runUrl(sequence, run, 'analysis.json'), { signal })
  if (!res.ok) throw new Error(`analysis.json for ${sequence}-${run}: HTTP ${res.status}`)
  return res.json()
}

/** Length of road filmed (km): GPS track length within each segment, gaps between segments not counted. */
export function filmedKm(a: Analysis) {
  let m = 0
  const bySegment = new Map<string, FrameRecord[]>()
  for (const f of a.frames) bySegment.set(f.segment, [...(bySegment.get(f.segment) ?? []), f])
  for (const frames of bySegment.values()) {
    frames.sort((x, y) => x.index - y.index)
    for (let i = 1; i < frames.length; i++) m += distance([frames[i - 1].lng, frames[i - 1].lat], [frames[i].lng, frames[i].lat])
  }
  return m / 1000
}

export function isCellId(id: string) {
  return /^[a-z][a-z-]*-\d+$/.test(id)
}

export function segmentLabel(a: Analysis, segment: string) {
  return a.sequence.segments.find((s) => s.name === segment)?.label ?? segment
}

export function segmentFrames(a: Analysis, segment: string) {
  return a.frames.filter((f) => f.segment === segment).sort((x, y) => x.index - y.index)
}

export function cellOfFrame(a: Analysis, index: number) {
  return a.cells.find((c) => c.frameIndexes.includes(index))
}

/** Frame inside a cell with the most to show (deepest dip, then kerb), for thumbnails and entry. */
export function bestFrame(a: Analysis, cell: CellRecord): FrameRecord {
  const frames = a.frames.filter((f) => cell.frameIndexes.includes(f.index))
  const score = (f: FrameRecord) => Math.max(0, ...f.dips.map((d) => d.depthCm * d.areaM2)) + (f.kerbs?.length ? 1 : 0) + f.potholes.length * 50
  return frames.reduce((best, f) => (score(f) > score(best) ? f : best), frames[Math.floor(frames.length / 2)])
}

export function nearestFrame(a: Analysis, lngLat: [number, number], maxM = 150): FrameRecord | null {
  let best: FrameRecord | null = null
  let bestD = maxM
  for (const f of a.frames) {
    const d = distance([f.lng, f.lat], lngLat)
    if (d < bestD) {
      bestD = d
      best = f
    }
  }
  return best
}

/** One line per cell along the drive, joined to the next cell so the track has no gaps. */
export function scanTrack(a: Analysis): FeatureCollection<LineString, { id: string; risk: number }> {
  const byIndex = new Map(a.frames.map((f) => [f.index, f]))
  const features: Feature<LineString, { id: string; risk: number }>[] = []
  a.cells.forEach((c, i) => {
    const coords = c.frameIndexes.map((ix) => byIndex.get(ix)).filter(Boolean).map((f) => [f!.lng, f!.lat])
    const next = a.cells[i + 1]
    if (next && next.segment === c.segment) {
      const first = byIndex.get(next.frameIndexes[0])
      if (first) coords.push([first.lng, first.lat])
    }
    if (coords.length >= 2) features.push({ type: 'Feature', properties: { id: c.id, risk: c.risk }, geometry: { type: 'LineString', coordinates: coords } })
  })
  return { type: 'FeatureCollection', features }
}

/** Geolocated dips found by the pipeline, for the map. */
export function dipPoints(a: Analysis): FeatureCollection<Point, { depthCm: number; areaM2: number }> {
  return {
    type: 'FeatureCollection',
    features: a.frames.flatMap((f) =>
      f.dips
        .filter((d) => d.lat !== null && d.lng !== null)
        .map<Feature<Point, { depthCm: number; areaM2: number }>>((d) => ({
          type: 'Feature',
          properties: { depthCm: d.depthCm, areaM2: d.areaM2 },
          geometry: { type: 'Point', coordinates: [d.lng!, d.lat!] },
        })),
    ),
  }
}
