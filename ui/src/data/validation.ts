// Output of backend/run_validate.py: FloodLens checked against publicly reported Delhi waterlogging hotspots.

import type { FeatureCollection, Point } from 'geojson'
import { ANALYSIS_BASE } from './analysis'
import type { Run } from './analysis'

export type ReferencePoint = { id: string; name: string; lat: number; lng: number; sources: string[]; approximate: boolean }

export type CellCheck = {
  run: Run
  cells: number
  cellsNearHotspot: number
  hotspotsCovered: { id: string; name: string }[]
  meanRiskNear: number | null
  meanRiskOther: number | null
  highRiskNear: number | null
  highRiskOther: number | null
  precisionTop5: number | null
  auc: number | null
  nearRadiusM: number
  highRiskThreshold: number
  perCell: { id: string; risk: number; nearest: string; nearestName: string; distanceM: number; near: boolean }[]
}

export type Validation = {
  generatedAt: string
  reference: {
    description: string
    count: number
    sources: Record<string, { title: string; url: string; kind: 'official' | 'reported' }>
    points: ReferencePoint[]
  }
  terrain: TerrainCheck
  terrainSurface: TerrainCheck
  hydrology: {
    radiusM: number
    hotspots: number
    controls: number
    features: Record<string, { label: string; auc: number; aucCi95: [number, number]; medianHotspots: number; medianControls: number }>
  }
  cells: Record<Run, CellCheck | null>
  caveats: string[]
}

export type TerrainCheck = {
  dem: 'bare' | 'surface'
  hotspots: number
  controls: number
  lowGroundThresholdM: number
  hitRate: number
  controlRate: number
  lift: number | null
  auc: number
  aucCi95: [number, number]
  hitRateCi95: [number, number]
  medianRelativeHotspotsM: number
  medianRelativeControlsM: number
  controlsRelativeM: number[]
  perHotspot: { id: string; name: string; relativeM: number; lowGround: boolean }[]
}

export async function loadValidation(signal?: AbortSignal): Promise<Validation> {
  const res = await fetch(`${ANALYSIS_BASE}/validation.json`, { signal })
  if (!res.ok) throw new Error(`validation.json: HTTP ${res.status}`)
  return res.json()
}

/** backend/validation/reference_<city>.geo.json, copied to data/outputs/reported-<city>.json. */
export type ReportedFile = {
  description: string
  sources: Record<string, { title: string; url: string; kind: 'official' | 'reported' }>
  hotspots: { id: string; name: string; lat: number; lng: number; sources: string[] }[]
}

/** A publicly reported waterlogging spot with its first source, for the map and the stretch panel. */
export type ReportedSpot = { id: string; name: string; lat: number; lng: number; official: boolean; source: { title: string; url: string } | null }

export function spotsFromValidation(v: Validation): ReportedSpot[] {
  return v.reference.points.map((p) => ({
    id: p.id,
    name: p.name,
    lat: p.lat,
    lng: p.lng,
    official: p.sources.some((s) => v.reference.sources[s]?.kind === 'official'),
    source: v.reference.sources[p.sources[0]] ?? null,
  }))
}

export function spotsFromFile(f: ReportedFile): ReportedSpot[] {
  return f.hotspots.map((p) => ({
    id: p.id,
    name: p.name,
    lat: p.lat,
    lng: p.lng,
    official: p.sources.some((s) => f.sources[s]?.kind === 'official'),
    source: f.sources[p.sources[0]] ?? null,
  }))
}

export function spotPoints(spots: ReportedSpot[]): FeatureCollection<Point, { id: string; name: string; official: boolean }> {
  return {
    type: 'FeatureCollection',
    features: spots.map((p) => ({
      type: 'Feature',
      properties: { id: p.id, name: p.name, official: p.official },
      geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
    })),
  }
}

export async function loadReported(file: string, signal?: AbortSignal): Promise<ReportedSpot[]> {
  const res = await fetch(`${ANALYSIS_BASE}/${file}`, { signal })
  if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`)
  return spotsFromFile(await res.json())
}

export function reportedPoints(f: ReportedFile): FeatureCollection<Point, { id: string; name: string; official: boolean }> {
  return {
    type: 'FeatureCollection',
    features: f.hotspots.map((p) => ({
      type: 'Feature',
      properties: { id: p.id, name: p.name, official: p.sources.some((s) => f.sources[s]?.kind === 'official') },
      geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
    })),
  }
}

export function referencePoints(v: Validation): FeatureCollection<Point, { id: string; name: string; official: boolean }> {
  return {
    type: 'FeatureCollection',
    features: v.reference.points.map((p) => ({
      type: 'Feature',
      properties: { id: p.id, name: p.name, official: p.sources.some((s) => v.reference.sources[s]?.kind === 'official') },
      geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
    })),
  }
}
