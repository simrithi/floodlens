import { useState } from 'react'
import { motion } from 'motion/react'
import {
  ArrowDown,
  CameraRotate,
  CloudRain,
  Drop,
  Mountains,
  Path,
  Pipe,
  Ruler,
  Warning,
  Waves,
} from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { HISTORY_YEARS, riskColor, riskLabel, waterLevel } from '../data/hotspots'
import type { Hotspot } from '../data/hotspots'
import { FACTOR_LABELS, bestFrame, nearestFrame, runUrl, segmentLabel } from '../data/analysis'
import type { CellRecord, Factors } from '../data/analysis'
import { AnimatedNumber } from '../ui/AnimatedNumber'
import { useAppState } from '../state'

function ScoreRing({ score, label, sub }: { score: number; label: string; sub: string }) {
  return (
    <div className="score-card" style={{ ['--c' as string]: riskColor(score) }}>
      <div className="score-ring">
        <svg viewBox="0 0 64 64">
          <circle cx="32" cy="32" r="27" className="ring-track" />
          <motion.circle
            cx="32"
            cy="32"
            r="27"
            className="ring-value"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: score / 100 }}
            transition={{ type: 'spring', stiffness: 60, damping: 18 }}
          />
        </svg>
        <span className="mono">{score}</span>
      </div>
      <div>
        <span className="score-label">{label}</span>
        <span className="score-sub">{sub}</span>
      </div>
    </div>
  )
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="metric">
      <span className="metric-label">
        {icon}
        {label}
      </span>
      <span className="metric-value mono">{value}</span>
    </div>
  )
}

function TabBar({ tabs, active, onChange }: { tabs: { id: string; label: string }[]; active: string; onChange: (id: string) => void }) {
  return (
    <div className="detail-tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={t.id === active}
          className={'detail-tab' + (t.id === active ? ' is-active' : '')}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

function StreetViewButton({ onOpen, reason }: { onOpen: (() => void) | null; reason: string }) {
  return (
    <button className={'btn street-btn' + (onOpen ? ' btn-primary' : '')} disabled={!onOpen} title={onOpen ? undefined : reason} onClick={onOpen ?? undefined}>
      <CameraRotate size={16} />
      Street view
      {!onOpen && <span className="soon">No footage</span>}
    </button>
  )
}

/** Sample hotspot (mock values), with street view when dashcam frames exist nearby. */
export function HotspotDetail({ hotspot }: { hotspot: Hotspot }) {
  const { rain, analysis, setStreetView } = useAppState()
  const level = waterLevel(hotspot, rain)
  const frame = analysis ? nearestFrame(analysis, hotspot.lngLat) : null
  const [tab, setTab] = useState<'factors' | 'history' | 'reasons'>('factors')

  return (
    <>
      <div className="detail-head">
        <span className="label mono">
          {hotspot.id} <span className="tag tag-sample">Sample data</span>
        </span>
        <h1 className="detail-name">{hotspot.name}</h1>
        <span className="detail-area">{hotspot.area}, New Delhi</span>
      </div>

      <ScoreRing score={hotspot.score} label={riskLabel(hotspot.score)} sub="Waterlogging risk score" />

      <div className="water-card">
        <div className="water-gauge" aria-hidden="true">
          <motion.div
            className="water-fill"
            initial={false}
            animate={{ scaleY: Math.min(1, level / 70) }}
            transition={{ type: 'spring', stiffness: 90, damping: 18 }}
          />
          <span className="gauge-mark" style={{ bottom: `${(30 / 70) * 100}%` }} />
        </div>
        <div className="water-text">
          <span className="label">Predicted standing water</span>
          <span className="water-value mono">
            <AnimatedNumber value={level} />
            <span className="unit"> cm</span>
          </span>
          <span className="water-note">
            {level >= 30 ? (
              <>
                <Warning size={14} weight="fill" /> Unsafe for two-wheelers
              </>
            ) : level > 0 ? (
              'Passable with care'
            ) : (
              'Dry at this rainfall'
            )}
          </span>
        </div>
      </div>

      <div>
        <TabBar
          tabs={[
            { id: 'factors', label: 'Risk factors' },
            { id: 'history', label: 'History' },
            { id: 'reasons', label: 'Why this spot' },
          ]}
          active={tab}
          onChange={(id) => setTab(id as typeof tab)}
        />

        {tab === 'factors' && (
          <div className="metrics tab-panel">
            <Metric icon={<Mountains size={16} />} label="Elevation" value={`${hotspot.elevation.toFixed(1)} m`} />
            <Metric icon={<ArrowDown size={16} />} label="Below surroundings" value={`${Math.abs(hotspot.relative).toFixed(1)} m`} />
            <Metric icon={<Ruler size={16} />} label="Road below kerb" value={`${hotspot.kerbDrop} cm`} />
            <Metric icon={<Drop size={16} />} label="Potholes" value={`${hotspot.potholes}`} />
            <Metric icon={<Pipe size={16} />} label="Drainage" value={hotspot.drainage} />
            <Metric icon={<CloudRain size={16} />} label="Rain now" value={`${rain} mm/hr`} />
          </div>
        )}

        {tab === 'history' && (
          <div className="tab-panel">
            <span className="label">Flooded in past monsoons</span>
            <div className="history">
              {HISTORY_YEARS.map((year, i) => (
                <span key={year} className={'history-cell' + (hotspot.history[i] ? ' is-flooded' : '')}>
                  <span className="history-bar" />
                  {year}
                </span>
              ))}
            </div>
          </div>
        )}

        {tab === 'reasons' && (
          <div className="tab-panel">
            <span className="label">Why this spot</span>
            <ul className="reasons">
              {hotspot.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <StreetViewButton
        onOpen={frame ? () => setStreetView({ segment: frame.segment, index: frame.index }) : null}
        reason="No dashcam frames within 150 m yet"
      />
    </>
  )
}

/** A measured ~60 m road stretch from the dashcam pipeline (real values). */
export function CellDetail({ cell }: { cell: CellRecord }) {
  const { analysis, run, setStreetView } = useAppState()
  if (!analysis) return null
  const frame = bestFrame(analysis, cell)
  const open = () => setStreetView({ segment: frame.segment, index: frame.index })
  const shot = new Date(frame.shotDate.replace(' ', 'T'))
  const [tab, setTab] = useState<'factors' | 'measurements'>('factors')

  return (
    <>
      <div className="detail-head">
        <span className="label mono">
          {cell.id.toUpperCase()} <span className="tag tag-measured">Measured</span>
        </span>
        <h1 className="detail-name">{segmentLabel(analysis, cell.segment)}</h1>
        <span className="detail-area">
          {Math.round(cell.startM)} m into the drive, {cell.frameIndexes.length} frames
        </span>
      </div>

      <button className="thumb" onClick={open} aria-label="Open street view at this stretch">
        <img src={runUrl(run, frame.overlay)} alt={`Dashcam frame ${frame.index} with detected road features`} />
        <span className="thumb-cta">
          <CameraRotate size={16} /> Street view
        </span>
      </button>

      <ScoreRing score={cell.risk} label={riskLabel(cell.risk)} sub="Risk from dashcam, terrain and rain" />

      <div>
        <TabBar
          tabs={[
            { id: 'factors', label: 'What drives the score' },
            { id: 'measurements', label: 'Measurements' },
          ]}
          active={tab}
          onChange={(id) => setTab(id as typeof tab)}
        />

        {tab === 'factors' && (
          <ul className="factors tab-panel">
            {(Object.keys(cell.factors) as (keyof Factors)[]).map((k) => (
              <li key={k}>
                <span className="factor-name">{FACTOR_LABELS[k]}</span>
                <span className="factor-bar">
                  <motion.span
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: cell.factors[k] }}
                    transition={{ type: 'spring', stiffness: 90, damping: 20 }}
                  />
                </span>
                <span className="factor-value mono">{Math.round(cell.factors[k] * 100)}</span>
              </li>
            ))}
          </ul>
        )}

        {tab === 'measurements' && (
          <div className="tab-panel">
            <div className="metrics">
              <Metric icon={<Waves size={16} />} label="Deepest dip" value={cell.maxDipCm ? `${cell.maxDipCm.toFixed(1)} cm` : 'None'} />
              <Metric icon={<Path size={16} />} label="Dip area / frame" value={`${cell.dipAreaM2.toFixed(1)} m²`} />
              <Metric icon={<Ruler size={16} />} label="Road below kerb" value={cell.kerbDropCm !== null ? `${cell.kerbDropCm.toFixed(1)} cm` : 'Not seen'} />
              <Metric icon={<Drop size={16} />} label="Potholes" value={`${cell.potholes}`} />
              <Metric icon={<Mountains size={16} />} label="Elevation" value={`${cell.demElevationM.toFixed(1)} m`} />
              <Metric icon={<ArrowDown size={16} />} label="Vs. 400 m around" value={`${cell.demRelativeM > 0 ? '+' : ''}${cell.demRelativeM.toFixed(1)} m`} />
            </div>
            <p className="fine-print">
              Recorded {shot.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}. Depths are
              single-camera estimates; kerb heights read low.
            </p>
          </div>
        )}
      </div>

      <StreetViewButton onOpen={open} reason="" />
    </>
  )
}
