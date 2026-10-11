import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { HOTSPOTS } from './data/hotspots'
import { loadAnalysis } from './data/analysis'
import type { Analysis, Run } from './data/analysis'
import { loadReported, loadValidation, spotsFromValidation } from './data/validation'
import type { ReportedSpot, Validation } from './data/validation'
import { initialLayers, saveLayers } from './data/layers'
import { SURVEYS, surveyById } from './data/surveys'
import { loadFindings } from './data/findings'
import type { Findings } from './data/findings'
import type { Survey, SurveyId } from './data/surveys'
import type { LayerId, LayerState } from './data/layers'

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
  /** Which dashcam survey (city + sequence) is shown. */
  survey: Survey
  setSurvey: (id: SurveyId) => void
  run: Run
  setRun: (r: Run) => void
  analysis: Analysis | null
  analysisStatus: AnalysisStatus
  streetView: StreetViewTarget | null
  setStreetView: (t: StreetViewTarget | null) => void
  /** Accuracy check against reported hotspots (null until loaded or if not generated). */
  validation: Validation | null
  /** Publicly reported waterlogging spots for the current survey's city (Delhi: the validation list). */
  reported: ReportedSpot[]
  /** Spots, causes and sized fixes for the current survey's city (null until loaded or not built). */
  findings: Findings | null
  showValidation: boolean
  setShowValidation: (v: boolean) => void
  /** Which map layers are switched on (dashboard only; remembered in this browser). */
  layers: LayerState
  setLayer: (id: LayerId, on: boolean) => void
}

const Ctx = createContext<AppState | null>(null)

/** ?survey=blr-orr in the address opens that survey (handy for demos and shared links). */
function initialSurvey(): SurveyId {
  const id = new URLSearchParams(window.location.search).get('survey')
  return SURVEYS.find((s) => s.id === id)?.id ?? 'delhi'
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [rain, setRain] = useState(75)
  const [selectedId, setSelectedId] = useState(HOTSPOTS[0].id)
  const [surveyId, setSurveyId] = useState<SurveyId>(initialSurvey)
  const survey = surveyById(surveyId)
  const [run, setRun] = useState<Run>('lth')
  const setSurvey = useCallback((id: SurveyId) => {
    setSurveyId(id)
    setRun((r) => (surveyById(id).runs.includes(r) ? r : 'lth'))
    setStreetView(null)
    const url = new URL(window.location.href)
    url.searchParams.set('survey', id)
    window.history.replaceState(window.history.state, '', url)
  }, [])
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analysisStatus, setAnalysisStatus] = useState<AnalysisStatus>('loading')
  const [streetView, setStreetView] = useState<StreetViewTarget | null>(null)
  const [validation, setValidation] = useState<Validation | null>(null)
  const [showValidation, setShowValidation] = useState(false)
  const [cityReported, setCityReported] = useState<ReportedSpot[]>([])
  const [findings, setFindings] = useState<Findings | null>(null)
  useEffect(() => {
    const ctrl = new AbortController()
    loadFindings(survey.city, ctrl.signal)
      .then(setFindings)
      .catch(() => !ctrl.signal.aborted && setFindings(null))
    return () => ctrl.abort()
  }, [survey.city])
  const [layers, setLayers] = useState<LayerState>(initialLayers)
  const setLayer = useCallback((id: LayerId, on: boolean) => {
    setLayers((prev) => {
      const next = { ...prev, [id]: on }
      saveLayers(next)
      return next
    })
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    loadValidation(ctrl.signal)
      .then(setValidation)
      .catch(() => setValidation(null))
    return () => ctrl.abort()
  }, [])

  // Reported spots for cities other than Delhi (data/outputs/reported-<city>.json).
  useEffect(() => {
    if (!survey.reported) {
      setCityReported([])
      return
    }
    const ctrl = new AbortController()
    loadReported(survey.reported, ctrl.signal)
      .then(setCityReported)
      .catch(() => !ctrl.signal.aborted && setCityReported([]))
    return () => ctrl.abort()
  }, [survey])
  const reported = useMemo(
    () => (survey.validation ? (validation ? spotsFromValidation(validation) : []) : cityReported),
    [survey, validation, cityReported],
  )

  // Pipeline output for the chosen run. Missing output (pipeline not run yet) leaves the app on sample data.
  useEffect(() => {
    const ctrl = new AbortController()
    setAnalysisStatus('loading')
    loadAnalysis(survey.sequence, run, ctrl.signal)
      .then((a) => {
        setAnalysis(a)
        setAnalysisStatus('ready')
        // Keep the selection if it belongs to this survey, else open its worst stretch (Delhi: first sample).
        setSelectedId((id) => {
          if (a.cells.some((c) => c.id === id)) return id
          if (survey.validation && HOTSPOTS.some((h) => h.id === id)) return id
          const worst = [...a.cells].sort((x, y) => y.risk - x.risk)[0]
          return survey.validation || !worst ? HOTSPOTS[0].id : worst.id
        })
      })
      .catch((e) => {
        if (ctrl.signal.aborted) return
        console.warn('FloodLens: no pipeline output, using sample data only.', e)
        setAnalysis(null)
        setAnalysisStatus('missing')
      })
    return () => ctrl.abort()
  }, [survey, run])

  const value = useMemo(
    () => ({
      rain, setRain, selectedId, setSelectedId, survey, setSurvey, run, setRun, analysis, analysisStatus, streetView, setStreetView,
      validation, reported, findings, showValidation, setShowValidation, layers, setLayer,
    }),
    [rain, selectedId, survey, setSurvey, run, analysis, analysisStatus, streetView, validation, reported, findings, showValidation, layers, setLayer],
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
