import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { HOTSPOTS } from './data/hotspots'
import { loadAnalysis } from './data/analysis'
import type { Analysis, Run } from './data/analysis'

export type Mode = 'landing' | 'app'

/** Which dashcam frame the street view shows. */
export type StreetViewTarget = { segment: string; index: number }

export type AnalysisStatus = 'loading' | 'ready' | 'missing'

type AppState = {
  rain: number
  setRain: (v: number) => void
  /** A sample hotspot id (WL-014) or a measured road cell id (ito-19). */
  selectedId: string
  setSelectedId: (id: string) => void
  run: Run
  setRun: (r: Run) => void
  analysis: Analysis | null
  analysisStatus: AnalysisStatus
  streetView: StreetViewTarget | null
  setStreetView: (t: StreetViewTarget | null) => void
}

const Ctx = createContext<AppState | null>(null)

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [rain, setRain] = useState(75)
  const [selectedId, setSelectedId] = useState(HOTSPOTS[0].id)
  const [run, setRun] = useState<Run>('lth')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus>('loading')
  const [streetView, setStreetView] = useState<StreetViewTarget | null>(null)

  // Pipeline output for the chosen run. Missing output (pipeline not run yet) leaves the app on sample data.
  useEffect(() => {
    const ctrl = new AbortController()
    setAnalysisStatus('loading')
    loadAnalysis(run, ctrl.signal)
      .then((a) => {
        setAnalysis(a)
        setAnalysisStatus('ready')
      })
      .catch((e) => {
        if (ctrl.signal.aborted) return
        console.warn('FloodLens: no pipeline output, using sample data only.', e)
        setAnalysis(null)
        setAnalysisStatus('missing')
      })
    return () => ctrl.abort()
  }, [run])

  const value = useMemo(
    () => ({ rain, setRain, selectedId, setSelectedId, run, setRun, analysis, analysisStatus, streetView, setStreetView }),
    [rain, selectedId, run, analysis, analysisStatus, streetView],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAppState() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAppState outside provider')
  return v
}

/** The selected sample hotspot, or null when a measured cell is selected. */
export function useSelectedHotspot() {
  const { selectedId } = useAppState()
  return HOTSPOTS.find((h) => h.id === selectedId) ?? null
}

/** The selected measured road cell, or null when a sample hotspot is selected. */
export function useSelectedCell() {
  const { selectedId, analysis } = useAppState()
  return analysis?.cells.find((c) => c.id === selectedId) ?? null
}
