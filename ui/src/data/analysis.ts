// Types and helpers for the backend pipeline output (backend/core/pipeline.py -> analysis.json).
// Real measurements from dashcam frames, unlike the sample data in hotspots.ts.

import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import { distance } from './geo'

export type Run = 'lth' | 'full'

export const RUNS: { id: Run; label: string }[] = [
  { id: 'lth', label: '1280p' },
  { id: 'full', label: '4K' },
]

export const SEQUENCE_ID = 4020141

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
  kerb: { dropCm: number; side: 'left' | 'right' } | null
  demElevationM: number
}

export type Factors = { terrain: number; surface: number; potholes: number; kerb: number; rain: number }

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
  demElevationM: number
  demRelativeM: number
  factors: Factors
  risk: number
}

export type Analysis = {
  version: number
  generatedAt: string
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

export const FACTOR_LABELS: Record<keyof Factors, string> = {
  terrain: 'Low ground (DEM)',
  surface: 'Road dips',
  potholes: 'Potholes',
  kerb: 'Road below kerb',
  rain: 'Heavy-rain history',
}

export function runUrl(run: Run, file = '') {
  return `${ANALYSIS_BASE}/${SEQUENCE_ID}-${run}/${file}`
}

export async function loadAnalysis(run: Run, signal?: AbortSignal): Promise<Analysis> {
  const res = await fetch(runUrl(run, 'analysis.json'), { signal })
  if (!res.ok) throw new Error(`analysis.json for ${run}: HTTP ${res.status}`)
  return res.json()
}

export function isCellId(id: string) {
  return /^[a-z]+-\d+$/.test(id)
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
  const score = (f: FrameRecord) => Math.max(0, ...f.dips.map((d) => d.depthCm * d.areaM2)) + (f.kerb ? 1 : 0) + f.potholes.length * 50
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
