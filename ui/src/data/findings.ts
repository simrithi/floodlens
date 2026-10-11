// Findings an official can act on (backend/scripts/build_findings.py -> data/outputs/findings-<city>.json):
// spots where water collects, why, what fixes it and how big the fix must be.

import { ANALYSIS_BASE } from './analysis'

export type Cause = 'channel' | 'sag' | 'hollow' | 'drain' | 'dip'
export type Priority = 'urgent' | 'high' | 'watch'
export type Confidence = 'high' | 'medium' | 'low'

export type Sizing = {
  targetCm: number
  rainMmHr: number
  governs: 'sag' | 'hollow' | 'sheet'
  areaM2: number
  /** Drain design standard credited at this spot (0 where the official map shows no drain). */
  designMmHr: number
  requiredMmHr: number | null
  requiredLs: number | null
}

export type Spot = {
  id: string
  name: string
  lat: number
  lng: number
  sequence: number
  cells: string[]
  worstCell: string
  directions: string[]
  cause: Cause
  causeLabel: string
  why: string
  fix: string
  now: string
  depthCm: Record<string, number>
  rainMmHr: Record<string, number>
  station: string
  sizing: Sizing
  drain: { distanceM: number; class: string; name: string; covered: boolean }
  evidence: { kind: 'repeat' | 'sag' | 'hollow' | 'catchment' | 'dip' | 'nodrain' | 'reported'; text: string }[]
  confidence: Confidence
  priority: Priority
  reported: { name: string; lat: number; lng: number; source: string | null; url: string | null; distanceM: number } | null
  frame: { index: number; segment: string; overlay: string; image: string }
  profile: { distanceM: number[]; elevationM: number[]; rimM: number } | null
}

export type Findings = {
  city: 'delhi' | 'bengaluru'
  cityName: string
  generatedAt: string
  surveys: { sequence: number; url: string; attribution: string; segments: string[]; date: string; stretches: number; sensorProfile: boolean }[]
  kmFilmed: number
  stretches: number
  flagCm: number
  stormSource: string
  drainsSource?: string
  drainStandard?: string
  spots: Spot[]
  method: string
}

export const PRIORITY: Record<Priority, { label: string; color: string; note: string }> = {
  urgent: { label: 'Urgent', color: '#ef4444', note: '20 cm or more, or 15 cm+ in an underpass or channel crossing' },
  high: { label: 'High', color: '#f97316', note: '10 to 20 cm' },
  watch: { label: 'Watch', color: '#facc15', note: '5 to 10 cm' },
}

export const CONFIDENCE: Record<Confidence, string> = {
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence',
}

export const CAUSE_SHORT: Record<Cause, string> = {
  channel: 'Channel crossing',
  sag: 'Road sag',
  hollow: 'Hollow, no drain',
  drain: 'Drain overwhelmed',
  dip: 'Surface dip',
}

export async function loadFindings(city: string, signal?: AbortSignal): Promise<Findings> {
  const res = await fetch(`${ANALYSIS_BASE}/findings-${city}.json`, { signal })
  if (!res.ok) throw new Error(`findings-${city}.json: HTTP ${res.status}`)
  return res.json()
}

export const outputUrl = (path: string) => `${ANALYSIS_BASE}/${path}`

/** The spot a measured stretch belongs to, if it was flagged. */
export function spotOfCell(f: Findings | null, cellId: string) {
  return f?.spots.find((s) => s.cells.includes(cellId)) ?? null
}
