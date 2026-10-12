import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Pause, Play, SkipForward, X } from '@phosphor-icons/react'
import { bestFrame } from '../data/analysis'
import type { Analysis, CellRecord } from '../data/analysis'
import { distance } from '../data/geo'
import type { ReportedSpot } from '../data/validation'
import { useAppState } from '../state'
import './tour.css'

/** Survey the walkthrough tells the story on. */
const TOUR_SURVEY = 'blr-orr' as const
const NEAR_M = 250

type Step = { caption: string; detail?: string; ms: number; run?: () => void }

const fmt = (n: number, digits = 0) => n.toFixed(digits)

/** The stretch with a reported spot nearby and the deepest phone-measured sag, and the worst stretch elsewhere. */
function pickStretches(a: Analysis, reported: ReportedSpot[]) {
  const near = (c: CellRecord) =>
    reported
      .map((r) => ({ r, d: distance([r.lng, r.lat], [c.lng, c.lat]) }))
      .filter((x) => x.d <= NEAR_M)
      .sort((x, y) => x.d - y.d)[0]
  const withReport = a.cells.filter((c) => near(c) && c.roadSag)
  const reportedCell = withReport.sort((x, y) => (y.roadSag?.depthM ?? 0) - (x.roadSag?.depthM ?? 0))[0]
  const elsewhere = a.cells
    .filter((c) => !reportedCell || distance([c.lng, c.lat], [reportedCell.lng, reportedCell.lat]) > 300)
    .sort((x, y) => y.risk - x.risk)[0]
  return { reportedCell, report: reportedCell ? near(reportedCell) : undefined, elsewhere }
}

/**
 * Scripted walkthrough for the demo video: a storm on the Bengaluru ORR survey, then the two places
 * where water collects, with the evidence for each. Every number comes from the loaded analysis.
 */
export function Tour({ onExit }: { onExit: () => void }) {
  const { analysis, survey, setSurvey, setRain, setSelectedId, setStreetView, reported, setLayer } = useAppState()
  const [step, setStep] = useState(0)
  const [paused, setPaused] = useState(false)
  const rainTimer = useRef(0)
  // The parent passes a new function each render; keep the latest without restarting timers.
  const exitRef = useRef(onExit)
  exitRef.current = onExit

  // Start on the tour survey with the layers the story needs.
  useEffect(() => {
    setSurvey(TOUR_SURVEY)
    setRain(0)
    setStreetView(null)
    for (const id of ['measured', 'water', 'flow', 'reported', 'drains', 'buildings'] as const) setLayer(id, true)
    return () => window.clearInterval(rainTimer.current)
  }, [setSurvey, setRain, setStreetView, setLayer])

  const ready = analysis?.sequence.id === survey.sequence && survey.id === TOUR_SURVEY

  const rampRain = useCallback(
    (to: number, ms: number) => {
      window.clearInterval(rainTimer.current)
      const start = performance.now()
      rainTimer.current = window.setInterval(() => {
        const t = Math.min(1, (performance.now() - start) / ms)
        setRain(Math.round(to * (1 - Math.pow(1 - t, 2))))
        if (t >= 1) window.clearInterval(rainTimer.current)
      }, 80)
    },
    [setRain],
  )

  const steps = useMemo<Step[]>(() => {
    if (!ready || !analysis) return []
    const { reportedCell, report, elsewhere } = pickStretches(analysis, reported)
    const storm = (reportedCell ?? elsewhere).water.designStorms[0]
    const out: Step[] = [
      {
        caption: `Bengaluru, Outer Ring Road. One ordinary dashcam drive, both directions: ${analysis.cells.length} stretches of road.`,
        detail: 'Footage: KartaView (CC BY-SA 4.0). No new survey needed.',
        ms: 6000,
        run: () => setSelectedId(elsewhere.id),
      },
      {
        caption: `A storm that comes every ${storm.returnPeriodYears} years: ${fmt(storm.rainMmHr)} mm/hr for 15 minutes.`,
        detail: `Rain gauge: ${(reportedCell ?? elsewhere).water.station}. Water columns show predicted standing water.`,
        ms: 6500,
        run: () => rampRain(Math.round(storm.rainMmHr), 4500),
      },
    ]
    if (reportedCell && reportedCell.roadSag) {
      const d2 = reportedCell.water.designStorms[0].depthCm
      out.push(
        {
          caption: `${report!.r.name}. The phone's tilt sensor felt the road drop ${fmt(reportedCell.roadSag.depthM, 1)} m and climb back out.`,
          detail: 'Satellite elevation (30 m grid) cannot see an underpass. The car can.',
          ms: 7500,
          run: () => setSelectedId(reportedCell.id),
        },
        {
          caption: `Runoff from ${reportedCell.roadSag.lengthM} m of road collects at the bottom: about ${fmt(d2)} cm of water.`,
          detail: `The official storm-drain map shows no drain within ${reportedCell.drain.distanceM} m. Flagged in both driving directions.`,
          ms: 7000,
        },
        {
          caption: `Reported waterlogged: ${report!.r.name}.`,
          detail: report!.r.source ? report!.r.source.title : undefined,
          ms: 6500,
        },
      )
    }
    if (elsewhere && elsewhere.id !== reportedCell?.id) {
      const parts = [
        elsewhere.hollowDepthCm >= 5 ? `the land dips ${fmt(elsewhere.hollowDepthCm)} cm` : null,
        elsewhere.roadSag ? `the road sags ${fmt(elsewhere.roadSag.depthM, 1)} m` : null,
        elsewhere.drain.distanceM <= 100 && elsewhere.catchmentM2 > 0 ? `a channel crosses ${elsewhere.drain.distanceM} m away` : null,
      ].filter(Boolean)
      out.push({
        caption: `${reportedCell ? `${Math.round(distance([elsewhere.lng, elsewhere.lat], [reportedCell.lng, reportedCell.lat]) / 100) * 100} m away, a` : 'A'} second low point: ${parts.join(', ')}.`,
        detail: `Predicted ${fmt(elsewhere.water.designStorms[0].depthCm)} cm in the same storm. Blue lines: where rain runs off the land.`,
        ms: 8000,
        run: () => setSelectedId(elsewhere.id),
      })
    }
    const evidence = reportedCell ?? elsewhere
    out.push(
      {
        caption: 'Every prediction links back to the frame it came from.',
        detail: 'Road, kerbs and dips detected in the dashcam image; nothing is drawn by hand.',
        ms: 7000,
        run: () => {
          setSelectedId(evidence.id)
          const f = bestFrame(analysis, evidence)
          setStreetView({ segment: f.segment, index: f.index })
        },
      },
      {
        caption: 'Varshik: find these spots before the monsoon, from footage cities already have.',
        detail: 'A screening tool for officials: check the flagged spots, clear the drains, plan the fixes.',
        ms: 7000,
        run: () => setStreetView(null),
      },
    )
    return out
  }, [ready, analysis, reported, rampRain, setSelectedId, setStreetView])

  // Run each step's action when it starts, then advance after its duration.
  useEffect(() => {
    const s = steps[step]
    if (!s) return
    s.run?.()
  }, [steps, step])

  useEffect(() => {
    if (paused || !steps.length) return
    if (step >= steps.length) {
      exitRef.current()
      return
    }
    const t = window.setTimeout(() => setStep((i) => i + 1), steps[step].ms)
    return () => window.clearTimeout(t)
  }, [steps, step, paused])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') exitRef.current()
      if (e.key === ' ') {
        e.preventDefault()
        setPaused((p) => !p)
      }
      if (e.key === 'ArrowRight') setStep((i) => i + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const current = steps[step]
  return (
    <div className="tour" role="region" aria-label="Walkthrough" aria-live="polite">
      <AnimatePresence mode="popLayout" initial={false}>
        {current ? (
          <motion.div
            key={step}
            className="tour-card glass"
            initial={{ opacity: 0, y: 14, filter: 'blur(6px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -8, filter: 'blur(6px)' }}
            transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className="tour-caption">{current.caption}</p>
            {current.detail && <p className="tour-detail">{current.detail}</p>}
          </motion.div>
        ) : (
          <motion.div key="wait" className="tour-card glass" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <p className="tour-detail">Loading the Bengaluru survey…</p>
          </motion.div>
        )}
      </AnimatePresence>
      <div className="tour-controls glass">
        <span className="mono tour-count">
          {Math.min(step + 1, steps.length || 1)}/{steps.length || 1}
        </span>
        <button onClick={() => setPaused((p) => !p)} aria-label={paused ? 'Resume walkthrough' : 'Pause walkthrough'}>
          {paused ? <Play size={14} weight="fill" /> : <Pause size={14} weight="fill" />}
        </button>
        <button onClick={() => setStep((i) => i + 1)} aria-label="Next step">
          <SkipForward size={14} weight="fill" />
        </button>
        <button onClick={onExit} aria-label="End walkthrough">
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
