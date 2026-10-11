import { motion } from 'motion/react'
import {
  ArrowDown,
  CameraRotate,
  CloudRain,
  Drop,
  Mountains,
  Pipe,
  MegaphoneSimple,
  Ruler,
  TrendDown,
  Warning,
  Waves,
} from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { HISTORY_YEARS, riskColor, riskLabel, waterLevel } from '../data/hotspots'
import type { Hotspot } from '../data/hotspots'
import { bestFrame, depthAt, isRamp, nearestFrame, rampText, runUrl, segmentLabel } from '../data/analysis'
import type { CellRecord } from '../data/analysis'
import { distance } from '../data/geo'
import { AnimatedNumber } from '../ui/AnimatedNumber'
import { spotOfCell } from '../data/findings'
import { FixCard } from './spots'
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

      <div className="metrics">
        <Metric icon={<Mountains size={16} />} label="Elevation" value={`${hotspot.elevation.toFixed(1)} m`} />
        <Metric icon={<ArrowDown size={16} />} label="Below surroundings" value={`${Math.abs(hotspot.relative).toFixed(1)} m`} />
        <Metric icon={<Ruler size={16} />} label="Road below kerb" value={`${hotspot.kerbDrop} cm`} />
        <Metric icon={<Drop size={16} />} label="Potholes" value={`${hotspot.potholes}`} />
        <Metric icon={<Pipe size={16} />} label="Drainage" value={hotspot.drainage} />
        <Metric icon={<CloudRain size={16} />} label="Rain now" value={`${rain} mm/hr`} />
      </div>

      <div>
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

      <div>
        <span className="label">Why this spot</span>
        <ul className="reasons">
          {hotspot.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>

      <StreetViewButton
        onOpen={frame ? () => setStreetView({ segment: frame.segment, index: frame.index }) : null}
        reason="No dashcam frames within 150 m yet"
      />
    </>
  )
}

/** A reported spot this close to a stretch is mentioned in its panel (reports are geocoded to ~150 m). */
const REPORTED_NEAR_M = 250

/** A measured ~60 m road stretch from the dashcam pipeline (real values). */
export function CellDetail({ cell }: { cell: CellRecord }) {
  const { analysis, run, setStreetView, rain, reported, setSelectedId, findings } = useAppState()
  // While the panel animates out after a survey switch it still holds the old stretch but already sees the
  // new survey's analysis: render nothing rather than mixing the two.
  if (!analysis || !analysis.cells.some((c) => c.id === cell.id)) return null
  const spot = spotOfCell(findings, cell.id)
  const level = depthAt(cell.water, rain)
  const nearby = reported
    .map((r) => ({ r, d: distance([r.lng, r.lat], [cell.lng, cell.lat]) }))
    .filter((x) => x.d <= REPORTED_NEAR_M)
    .sort((a, b) => a.d - b.d)[0]
  const frame = bestFrame(analysis, cell)
  const open = () => setStreetView({ segment: frame.segment, index: frame.index })
  const shot = new Date(frame.shotDate.replace(' ', 'T'))

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
        {nearby && (
          <span className="reported-near">
            <MegaphoneSimple size={14} weight="fill" />
            <span>
              Reported waterlogged: <b>{nearby.r.name}</b>, {Math.round(nearby.d / 10) * 10} m away
              {nearby.r.source && (
                <>
                  {' '}
                  (
                  <a href={nearby.r.source.url} target="_blank" rel="noreferrer">
                    source
                  </a>
                  )
                </>
              )}
            </span>
          </span>
        )}
      </div>

      <button className="thumb" onClick={open} aria-label="Open street view at this stretch">
        <img src={runUrl(analysis.sequence.id, run, frame.overlay)} alt={`Dashcam frame ${frame.index} with detected road features`} />
        <span className="thumb-cta">
          <CameraRotate size={16} /> Street view
        </span>
      </button>

      <ScoreRing
        score={cell.risk}
        label={isRamp(cell) ? 'Runs off downhill' : riskLabel(cell.risk)}
        sub={`${cell.depth2yCm.toFixed(0)} cm of water in a 2-year storm (30 cm = 100)`}
      />
      {cell.drainsTo && isRamp(cell) && (
        <button className="ramp-note" onClick={() => setSelectedId(cell.drainsTo!.id)}>
          <TrendDown size={16} />
          <span>
            {rampText(cell.drainsTo)}. <span className="ramp-link">Show the low point</span>
          </span>
        </button>
      )}

      {spot && <FixCard spot={spot} waterM={depthAt((analysis.cells.find((c) => c.id === spot.worstCell) ?? cell).water, rain) / 100} />}

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
          <span className="label">Predicted standing water at {rain} mm/hr</span>
          <span className="water-value mono">
            <AnimatedNumber value={level} />
            <span className="unit"> cm</span>
          </span>
          <span className="water-note">
            {level >= 30 ? (
              <>
                <Warning size={14} weight="fill" /> Unsafe for two-wheelers
              </>
            ) : level >= 2 ? (
              'Passable with care'
            ) : (
              'Drains at this rainfall'
            )}
          </span>
        </div>
      </div>

      <div>
        <span className="label">Design storms, {cell.water.station} rain gauge (15-min burst)</span>
        <div className="storms">
          {cell.water.designStorms.map((s) => (
            <div key={s.returnPeriodYears} className="storm">
              <span className="storm-t">Every {s.returnPeriodYears} yrs</span>
              <span className="mono storm-rain">{s.rainMmHr.toFixed(0)} mm/hr</span>
              <span className="mono storm-depth" style={{ color: riskColor(Math.min(100, (s.depthCm / 30) * 100)) }}>
                {s.depthCm.toFixed(0)} cm
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="metrics">
        <Metric
          icon={<Pipe size={16} />}
          label="Nearest storm drain"
          value={`${cell.drain.distanceM} m${['primary', 'secondary', 'tertiary'].includes(cell.drain.class) ? `, ${cell.drain.class}` : ''}${cell.drain.covered ? ', covered' : ''}`}
        />
        <Metric icon={<ArrowDown size={16} />} label="Land draining here" value={`${(cell.catchmentM2 / 10000).toLocaleString('en-IN', { maximumFractionDigits: 1 })} ha`} />
        {!spot && cell.roadSag && (
          <Metric icon={<TrendDown size={16} />} label="Sag in the road" value={`${cell.roadSag.depthM.toFixed(1)} m over ${cell.roadSag.lengthM} m`} />
        )}
        {!spot && cell.hollowDepthCm >= 5 && <Metric icon={<Mountains size={16} />} label="Hollow in the land" value={`${cell.hollowDepthCm.toFixed(0)} cm deep`} />}
        {cell.maxDipCm > 0 && <Metric icon={<Waves size={16} />} label="Deepest dip" value={`${cell.maxDipCm.toFixed(1)} cm`} />}
        {cell.potholes > 0 && <Metric icon={<Drop size={16} />} label="Potholes" value={`${cell.potholes}`} />}
      </div>

      <p className="fine-print">
        Recorded {shot.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}. Screening model: dip depths are
        single-camera estimates; road sags come from the phone's tilt sensor and are noisy, so treat one as a lead to check; drains are credited with the city's documented design standard where one serves the road (none where the official drain map shows none), no blockage or
        pipe flow is modelled.
      </p>

      <StreetViewButton onOpen={open} reason="" />
    </>
  )
}
