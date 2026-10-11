import { useEffect, useState } from 'react'
import { ANALYSIS_BASE } from '../data/analysis'

/** Survey corridor facts: length, km filmed, elevation (backend/scripts/export_map_layers.py). */
export type RouteProfile = {
  source: string
  lengthM: number
  filmedM: number
  hollowRule?: string
  points: { d: number; e: number; hollowCm: number; inHollow?: boolean; filmed: boolean }[]
}

export function useRouteProfile() {
  const [profile, setProfile] = useState<RouteProfile | null>(null)
  useEffect(() => {
    const ctrl = new AbortController()
    fetch(`${ANALYSIS_BASE}/route_profile.json`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then(setProfile)
      .catch(() => setProfile(null))
    return () => ctrl.abort()
  }, [])
  return profile
}
