import { motion } from 'motion/react'
import { useId } from 'react'
import { ArrowRight, CheckCircle, Drop, Eye, Megaphone, Mountains, Path, Pipe, Repeat, TrendDown, Waves, Wrench } from '@phosphor-icons/react'
import type { Icon } from '@phosphor-icons/react'
import { CAUSE_SHORT, CONFIDENCE, PRIORITY } from '../data/findings'
import type { Findings, Spot } from '../data/findings'
import { SURVEYS } from '../data/surveys'
import { useAppState } from '../state'
import { ActionsBlock, FrameCheckBlock } from './aws-panels'

const ease = [0.16, 1, 0.3, 1] as const

const EVIDENCE_ICON: Record<Spot['evidence'][number]['kind'], Icon> = {
  repeat: Repeat,
  sag: TrendDown,
  hollow: Mountains,
  catchment: Waves,
  dip: Path,
  nodrain: Pipe,
  reported: Megaphone,
}

export function PriorityBadge({ spot }: { spot: Spot }) {
  const p = PRIORITY[spot.priority]
  return (
    <span className="prio-badge" style={{ ['--c' as string]: p.color }}>
      {p.label}
    </span>
  )
}

/** Select a spot: switch to its survey if needed, then open its worst stretch. */
export function useOpenSpot() {
  const { survey, setSurvey, setSelectedId } = useAppState()
  return (spot: Spot) => {
    setSelectedId(spot.worstCell)
    if (spot.sequence !== survey.sequence) {
      const s = SURVEYS.find((x) => x.sequence === spot.sequence)
      if (s) setSurvey(s.id)
    }
  }
}

/** Left panel: where to act first. */
export function PriorityList({ findings, selectedId }: { findings: Findings; selectedId: string }) {
  const open = useOpenSpot()
  if (!findings.spots.length) return <p className="empty">No stretch holds {findings.flagCm} cm or more in a 2-year storm.</p>
  return (
    <ol className="prio-list">
      {findings.spots.map((s, i) => {
        const active = s.cells.includes(selectedId)
        return (
          <motion.li key={s.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 * i, duration: 0.4, ease }}>
            <button className={'prio-item' + (active ? ' is-selected' : '')} onClick={() => open(s)}>
              <span className="prio-rank mono" style={{ ['--c' as string]: PRIORITY[s.priority].color }}>
                {s.id}
              </span>
              <span className="prio-text">
                <span className="prio-name">{s.name}</span>
                <span className="prio-meta">
                  {`${CAUSE_SHORT[s.cause]}, ${s.depthCm['2'].toFixed(0)} cm${s.sizing.requiredLs != null ? `, needs ${s.sizing.requiredLs} L/s` : ''}`}
                </span>
              </span>
              <PriorityBadge spot={s} />
            </button>
          </motion.li>
        )
      })}
    </ol>
  )
}

/** Road profile measured by the phone, with the water that collects at the bottom. Height exaggerated. */
export function ProfileChart({ profile, waterM, height = 120, width = 320 }: { profile: NonNullable<Spot['profile']>; waterM: number; height?: number; width?: number }) {
  const id = useId()
  const W = width
  const H = height
  const pad = { l: 4, r: 4, t: 10, b: 18 }
  const xs = profile.distanceM
  const ys = profile.elevationM
  const x0 = xs[0]
  const x1 = xs[xs.length - 1]
  const lo = Math.min(...ys) - 0.4
  const hi = Math.max(...ys, profile.rimM) + 0.3
  const sx = (x: number) => pad.l + ((x - x0) / (x1 - x0)) * (W - pad.l - pad.r)
  const sy = (y: number) => pad.t + (1 - (y - lo) / (hi - lo)) * (H - pad.t - pad.b)
  const road = xs.map((x, i) => `${i ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(ys[i]).toFixed(1)}`).join(' ')
  const ground = `${road} L${sx(x1)},${H - pad.b} L${sx(x0)},${H - pad.b} Z`
  const level = Math.min(waterM, profile.rimM)
  // Water polygon: the stretch around the bottom (x = 0) that lies below the water level.
  const bottom = xs.findIndex((x) => x >= 0)
  let a = bottom
  let b = a
  while (a > 0 && ys[a - 1] < level) a--
  while (b < xs.length - 1 && ys[b + 1] < level) b++
  const pts = []
  for (let i = a; i <= b; i++) pts.push(`${sx(xs[i]).toFixed(1)},${sy(ys[i]).toFixed(1)}`)
  const water = level > 0.005 ? `M${sx(xs[a])},${sy(level)} L${pts.join(' L')} L${sx(xs[b])},${sy(level)} Z` : ''
  // Pixels per metre up, over pixels per metre along: how much the dip is stretched to be visible.
  const vertical = (H - pad.t - pad.b) / (hi - lo) / ((W - pad.l - pad.r) / (x1 - x0))
  return (
    <figure className="profile-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Road profile: the road dips ${ys.length ? (Math.max(...ys) - Math.min(...ys)).toFixed(1) : 0} m`}>
        <defs>
          <linearGradient id={`${id}-g`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" className="pg-top" />
            <stop offset="1" className="pg-bottom" />
          </linearGradient>
        </defs>
        <path d={ground} fill={`url(#${id}-g)`} />
        <line x1={pad.l} x2={W - pad.r} y1={sy(profile.rimM)} y2={sy(profile.rimM)} className="profile-rim" />
        <text x={W - pad.r - 2} y={sy(profile.rimM) - 4} textAnchor="end" className="profile-label">
          spills over at {profile.rimM.toFixed(1)} m
        </text>
        {water && <motion.path d={water} className="profile-water" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }} />}
        {water && (
          <g className="profile-callout">
            <line x1={sx(0)} x2={sx(0)} y1={sy(level) - 4} y2={sy(level) - 18} />
            <text x={sx(0)} y={sy(level) - 22} textAnchor="middle">
              {Math.round(level * 100)} cm of water
            </text>
          </g>
        )}
        <motion.path d={road} className="profile-road" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, ease }} />
        <text x={pad.l} y={H - 4} className="profile-label">
          {x0} m
        </text>
        <text x={sx(0)} y={H - 4} textAnchor="middle" className="profile-label">
          lowest point
        </text>
        <text x={W - pad.r} y={H - 4} textAnchor="end" className="profile-label">
          +{x1} m
        </text>
      </svg>
      <figcaption>Measured by the phone's tilt sensor. Height exaggerated about {Math.round(vertical)}x.</figcaption>
    </figure>
  )
}

/** How much drainage the spot needs to stay passable. Today's real drain capacity is not published, so
 *  it is not shown; the litres per second follow from the storm and the measured ground alone. */
export function CapacityBars({ spot }: { spot: Spot }) {
  const z = spot.sizing
  if (z.requiredLs == null) return null
  return (
    <div className="capacity">
      <div className="capacity-need">
        <span className="capacity-label">Drainage needed to stay under {z.targetCm} cm</span>
        <motion.span className="mono capacity-big" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }}>
          {z.requiredLs} <small>L/s</small>
        </motion.span>
      </div>
      <span className="capacity-track">
        <motion.span className="capacity-fill need" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 1.1, ease }} />
      </span>
      <p className="capacity-note">
        For the 2-year storm ({z.rainMmHr.toFixed(0)} mm/hr for 15 min) on {z.areaM2.toLocaleString('en-IN')} m² draining here. Today's drain capacity is not
        published, so it is not shown.
      </p>
    </div>
  )
}

/** Right panel: why this spot floods and what fixes it. */
export function FixCard({ spot, waterM, city, action }: { spot: Spot; waterM: number; city?: string; action?: string }) {
  return (
    <motion.section className="fix-card" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease }}>
      <header className="fix-head">
        <span className="label mono">
          Spot {spot.id}
        </span>
        <PriorityBadge spot={spot} />
        <span className="fix-conf">
          <Eye size={12} /> {CONFIDENCE[spot.confidence]}
        </span>
      </header>
      <h2 className="fix-cause">{spot.causeLabel}</h2>

      <div className="fix-block">
        <span className="fix-step">
          <Drop size={14} weight="fill" /> Why water collects here
        </span>
        <p>{spot.why}</p>
        {spot.profile && <ProfileChart profile={spot.profile} waterM={waterM} />}
        <ul className="evidence">
          {spot.evidence.map((e) => {
            const I = EVIDENCE_ICON[e.kind]
            return (
              <li key={e.kind}>
                <I size={14} /> {e.text}
              </li>
            )
          })}
        </ul>
      </div>

      <div className="fix-block">
        <span className="fix-step">
          <Wrench size={14} weight="fill" /> What fixes it
        </span>
        <CapacityBars spot={spot} />
        <p>{spot.fix.split('. Drainage here')[0]}.</p>
        <p className="fix-now">
          <CheckCircle size={14} weight="fill" /> {spot.now}
        </p>
      </div>
      {city && <FrameCheckBlock city={city} spotId={spot.id} />}
      {city && <ActionsBlock city={city} spotId={spot.id} action={action} />}
      {spot.directions.length > 1 && (
        <p className="fix-foot">
          <ArrowRight size={12} /> Seen on {spot.directions.length} passes: {spot.directions.join('; ')}
        </p>
      )}
    </motion.section>
  )
}
