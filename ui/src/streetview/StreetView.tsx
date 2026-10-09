import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import {
  ArrowLeft,
  CaretLeft,
  CaretRight,
  Compass,
  MapPin,
  Pause,
  Play,
  Ruler,
  Warning,
  Waves,
  X,
} from '@phosphor-icons/react'
import { RUNS, cellOfFrame, runUrl, segmentFrames, segmentLabel } from '../data/analysis'
import type { FrameRecord, Run } from '../data/analysis'
import { riskColor, riskLabel } from '../data/hotspots'
import { useAppState } from '../state'
import './streetview.css'

type View = 'findings' | 'original' | 'depth' | 'compare'

const VIEWS: { id: View; label: string; key: string }[] = [
  { id: 'findings', label: 'Findings', key: '1' },
  { id: 'original', label: 'Original', key: '2' },
  { id: 'depth', label: 'AI depth', key: '3' },
  { id: 'compare', label: 'Compare', key: '4' },
]

const PLAY_FPS = 5

function imageFor(frame: FrameRecord, view: Exclude<View, 'compare'>) {
  return view === 'findings' ? frame.overlay : view === 'depth' ? frame.depth : frame.image
}

/** Image that keeps showing the previous picture until the next one has loaded, then cross-fades. */
function FadeImage({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [shown, setShown] = useState(src)
  const [pending, setPending] = useState<string | null>(null)
  useEffect(() => {
    if (src === shown) return
    const img = new Image()
    img.src = src
    img.onload = () => setPending(src)
    return () => {
      img.onload = null
    }
  }, [src, shown])
  return (
    <div className={'fade-image ' + (className ?? '')}>
      <img src={shown} alt={alt} draggable={false} />
      {pending && (
        <img
          key={pending}
          src={pending}
          alt=""
          draggable={false}
          className="fade-in"
          onAnimationEnd={() => {
            setShown(pending)
            setPending(null)
          }}
        />
      )}
    </div>
  )
}

function CompareView({ frame, run }: { frame: FrameRecord; run: Run }) {
  const [split, setSplit] = useState(50)
  const ref = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const drag = useCallback((clientX: number) => {
    const r = ref.current?.getBoundingClientRect()
    if (r) setSplit(Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100)))
  }, [])
  return (
    <div
      ref={ref}
      className="compare"
      onPointerDown={(e) => {
        dragging.current = true
        e.currentTarget.setPointerCapture(e.pointerId)
        drag(e.clientX)
      }}
      onPointerMove={(e) => dragging.current && drag(e.clientX)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      <FadeImage src={runUrl(run, frame.image)} alt="Original dashcam frame" />
      <div className="compare-top" style={{ clipPath: `inset(0 0 0 ${split}%)` }}>
        <FadeImage src={runUrl(run, frame.overlay)} alt="Frame with detected road features" />
      </div>
      <div className="compare-handle" style={{ left: `${split}%` }}>
        <span>
          <CaretLeft size={12} weight="bold" />
          <CaretRight size={12} weight="bold" />
        </span>
      </div>
      <span className="compare-tag left">Original</span>
      <span className="compare-tag right">Findings</span>
    </div>
  )
}

export function StreetView() {
  const { analysis, streetView, setStreetView, run, setRun, setSelectedId } = useAppState()
  const reduced = useReducedMotion()
  const [view, setView] = useState<View>('findings')
  const [playing, setPlaying] = useState(false)

  const frames = useMemo(() => (analysis && streetView ? segmentFrames(analysis, streetView.segment) : []), [analysis, streetView])
  const pos = Math.max(0, frames.findIndex((f) => f.index === streetView?.index))
  const frame = frames[pos]

  const go = useCallback(
    (i: number) => {
      const f = frames[Math.min(frames.length - 1, Math.max(0, i))]
      if (f && streetView) setStreetView({ segment: streetView.segment, index: f.index })
    },
    [frames, streetView, setStreetView],
  )

  const close = useCallback(() => {
    setPlaying(false)
    if (analysis && frame) {
      const cell = cellOfFrame(analysis, frame.index)
      if (cell) setSelectedId(cell.id)
    }
    setStreetView(null)
  }, [analysis, frame, setSelectedId, setStreetView])

  // Playback: drive through the segment.
  useEffect(() => {
    if (!playing) return
    if (pos >= frames.length - 1) {
      setPlaying(false)
      return
    }
    const t = window.setTimeout(() => go(pos + 1), 1000 / PLAY_FPS)
    return () => window.clearTimeout(t)
  }, [playing, pos, frames.length, go])

  // Preload the next frames so stepping and playback stay smooth.
  useEffect(() => {
    if (!frame) return
    for (const f of frames.slice(pos + 1, pos + 4)) {
      const img = new Image()
      img.src = runUrl(run, view === 'compare' || view === 'findings' ? f.overlay : view === 'depth' ? f.depth : f.image)
    }
  }, [frame, frames, pos, run, view])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement && e.key !== 'Escape') return
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowRight') go(pos + 1)
      else if (e.key === 'ArrowLeft') go(pos - 1)
      else if (e.key === ' ') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else {
        const v = VIEWS.find((x) => x.key === e.key)
        if (v) setView(v.id)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close, go, pos])

  if (!analysis || !frame) return null
  const cell = cellOfFrame(analysis, frame.index)
  const time = frame.shotDate.slice(11, 19)

  return (
    <motion.div
      className="sv-backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.25 } }}
      transition={{ duration: reduced ? 0 : 0.3 }}
    >
      <motion.div
        className="sv"
        role="dialog"
        aria-modal="true"
        aria-label="Street view"
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 10 }}
        transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 160, damping: 24 }}
      >
        <header className="sv-head">
          <button className="btn" onClick={close}>
            <ArrowLeft size={16} /> Map
          </button>
          <div className="sv-title">
            <span className="sv-name">{segmentLabel(analysis, frame.segment)}</span>
            <span className="sv-sub mono">
              Frame {pos + 1} of {frames.length}, {time}
            </span>
          </div>
          <div className="sv-views" role="tablist" aria-label="View">
            {VIEWS.map((v) => (
              <button key={v.id} role="tab" aria-selected={view === v.id} className={view === v.id ? 'is-active' : ''} onClick={() => setView(v.id)}>
                {v.label}
              </button>
            ))}
          </div>
          <div className="seg-toggle" role="group" aria-label="Resolution">
            {RUNS.map((r) => (
              <button key={r.id} className={run === r.id ? 'is-active' : ''} onClick={() => setRun(r.id)}>
                {r.label}
              </button>
            ))}
          </div>
          <button className="sv-close" onClick={close} aria-label="Close street view">
            <X size={18} />
          </button>
        </header>

        <div className="sv-body">
          <div className="sv-stage">
            {view === 'compare' ? (
              <CompareView frame={frame} run={run} />
            ) : (
              <FadeImage src={runUrl(run, imageFor(frame, view))} alt={`Dashcam frame ${frame.index}, ${view} view`} />
            )}
            <button className="sv-nav prev" onClick={() => go(pos - 1)} disabled={pos === 0} aria-label="Previous frame">
              <CaretLeft size={22} weight="bold" />
            </button>
            <button className="sv-nav next" onClick={() => go(pos + 1)} disabled={pos === frames.length - 1} aria-label="Next frame">
              <CaretRight size={22} weight="bold" />
            </button>
            {view === 'depth' && (
              <div className="depth-key">
                <span>Far</span>
                <span className="depth-ramp" />
                <span>Near</span>
              </div>
            )}
          </div>

          <aside className="sv-info">
            {cell && (
              <button className="sv-cell" style={{ ['--c' as string]: riskColor(cell.risk) }} onClick={close}>
                <span className="sv-cell-score mono">{cell.risk}</span>
                <span>
                  <span className="sv-cell-label">{riskLabel(cell.risk)}</span>
                  <span className="sv-cell-id mono">Stretch {cell.id}, show on map</span>
                </span>
              </button>
            )}

            <div className="sv-section">
              <span className="label">In this frame</span>
              <AnimatePresence mode="popLayout" initial={false}>
                <motion.ul
                  key={frame.index}
                  className="findings"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  {frame.dips.map((d, i) => (
                    <li key={`d${i}`} className="finding water">
                      <Waves size={16} />
                      <span>
                        Dip <b className="mono">{d.depthCm.toFixed(0)} cm</b> deep, {d.areaM2.toFixed(1)} m²
                        <small>{d.distanceM.toFixed(0)} m ahead</small>
                      </span>
                    </li>
                  ))}
                  {frame.potholes.map((p, i) => (
                    <li key={`p${i}`} className="finding pothole">
                      <Warning size={16} />
                      <span>
                        Pothole <b className="mono">{Math.round(p.confidence * 100)}%</b>
                        <small>{p.areaM2.toFixed(1)} m²</small>
                      </span>
                    </li>
                  ))}
                  {frame.kerb && (
                    <li className="finding kerb">
                      <Ruler size={16} />
                      <span>
                        Road <b className="mono">{frame.kerb.dropCm.toFixed(0)} cm</b> below kerb
                        <small>{frame.kerb.side} side</small>
                      </span>
                    </li>
                  )}
                  {!frame.dips.length && !frame.potholes.length && !frame.kerb && <li className="finding none">Nothing measurable in range</li>}
                </motion.ul>
              </AnimatePresence>
            </div>

            <dl className="sv-meta">
              <div>
                <dt>
                  <MapPin size={14} /> Position
                </dt>
                <dd className="mono">
                  {frame.lat.toFixed(5)}, {frame.lng.toFixed(5)}
                </dd>
              </div>
              <div>
                <dt>
                  <Compass size={14} /> Heading
                </dt>
                <dd className="mono">{frame.heading !== null ? `${Math.round(frame.heading)}°` : 'n/a'}</dd>
              </div>
              <div>
                <dt>Elevation</dt>
                <dd className="mono">{frame.demElevationM.toFixed(1)} m</dd>
              </div>
              <div>
                <dt>Road visible</dt>
                <dd className="mono">{Math.round(frame.roadFraction * 100)}%</dd>
              </div>
            </dl>

            <p className="sv-credit">
              Imagery:{' '}
              <a href={analysis.sequence.url} target="_blank" rel="noreferrer">
                KartaView
              </a>
              , {analysis.sequence.attribution}, {analysis.sequence.license}. Overlays by FloodLens, same licence. Single-camera estimates.
            </p>
          </aside>
        </div>

        <footer className="sv-timeline">
          <button className="sv-play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play drive'}>
            {playing ? <Pause size={18} weight="fill" /> : <Play size={18} weight="fill" />}
          </button>
          <div className="sv-track">
            <div className="sv-marks" aria-hidden="true">
              {frames.map((f, i) => {
                const kind = f.potholes.length ? 'pothole' : f.dips.length ? 'water' : f.kerb ? 'kerb' : null
                return kind ? <span key={f.index} className={`mark ${kind}`} style={{ left: `${(i / Math.max(1, frames.length - 1)) * 100}%` }} /> : null
              })}
            </div>
            <input
              type="range"
              min={0}
              max={frames.length - 1}
              value={pos}
              onChange={(e) => go(Number(e.target.value))}
              style={{ ['--p' as string]: `${(pos / Math.max(1, frames.length - 1)) * 100}%` }}
              aria-label="Frame"
            />
          </div>
          <span className="sv-legend">
            <span className="mark water" /> Dip <span className="mark kerb" /> Kerb <span className="mark pothole" /> Pothole
          </span>
        </footer>
      </motion.div>
    </motion.div>
  )
}
