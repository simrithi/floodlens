// Client for the AWS Lambda Function URLs behind the frame check (prompt 3), officer brief (4),
// tomorrow's alert (5) and officer actions (6). Each URL is a build-time env var; when one is not set
// the matching feature is hidden instead of showing a button that cannot work.

import { ANALYSIS_BASE } from './analysis'

export const API = {
  frameCheck: import.meta.env.VITE_API_FRAME_CHECK as string | undefined,
  brief: import.meta.env.VITE_API_BRIEF as string | undefined,
  actions: import.meta.env.VITE_API_ACTIONS as string | undefined,
}

export type Answer = 'yes' | 'no' | 'unclear'

export type FrameCheck = {
  underpass: Answer
  drainInletVisible: Answer
  inletCondition: 'clear' | 'partly blocked' | 'blocked' | 'not visible'
  blockage: string[]
  standingWaterOrStain: Answer
  kerbOpeningsVisible: Answer
  notes: string
  framesUsed: (string | number)[]
  model: string
  generatedAt: string
}

export type Brief = { city: string; language: 'en' | 'hi'; text: string; model: string; generatedAt: string }

export type AlertSpot = { spotId: string; name: string; forecastRainMmHr: number; expectedDepthCm: number; action: string; note?: string }
export type Alert = { city: string; date: string; generatedAt: string; spots: AlertSpot[] }

export type ActionItem = {
  pk: string
  sk: string
  spotId: string
  kind: 'approval' | 'observation'
  recordedAt: string
  approved?: boolean
  note?: string
  flooded?: boolean
  depthCm?: number | string
  date?: string
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T | null> {
  const res = await fetch(url, { signal })
  if (res.status === 404 || res.status === 403) return null
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`)
  return data as T
}

// Cached results live next to the analysis files, so reading them needs no Lambda call.
export const cachedFrameCheck = (city: string, spotId: string, signal?: AbortSignal) =>
  getJson<FrameCheck>(`${ANALYSIS_BASE}/checks/${city}/${spotId}.json`, signal)
export const runFrameCheck = (city: string, spotId: string, refresh = false) =>
  post<FrameCheck>(API.frameCheck!, { city, spotId, refresh })

export const cachedBrief = (city: string, language: string, signal?: AbortSignal) =>
  getJson<Brief>(`${ANALYSIS_BASE}/briefs/${city}-${language}.json`, signal)
export const generateBrief = (city: string, language: string, refresh = false) =>
  post<Brief>(API.brief!, { city, language, refresh })

/** Tomorrow's alert, written by the daily forecast Lambda (the date is tomorrow in UTC, as there). */
export function loadAlert(city: string, signal?: AbortSignal) {
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10)
  return getJson<Alert>(`${ANALYSIS_BASE}/alerts/${city}-${tomorrow}.json`, signal)
}

export async function listActions(city: string, signal?: AbortSignal): Promise<ActionItem[]> {
  if (!API.actions) return []
  const res = await fetch(`${API.actions}?city=${city}`, { signal })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()).items as ActionItem[]
}

type Write = { city: string; spotId: string; passcode: string } & (
  | { kind: 'approval'; approved: boolean; note?: string }
  | { kind: 'observation'; flooded: boolean; depthCm?: number; date?: string }
)
export const recordAction = (w: Write) => post<{ recorded: boolean }>(API.actions!, w)

// The officer passcode is typed by the officer and kept for the tab only.
export const getPasscode = () => {
  try {
    return sessionStorage.getItem('floodlens-passcode') ?? ''
  } catch {
    return ''
  }
}
export const setPasscode = (p: string) => {
  try {
    sessionStorage.setItem('floodlens-passcode', p)
  } catch {
    /* private mode: ask again next time */
  }
}
