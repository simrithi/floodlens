import { motion, useReducedMotion } from 'motion/react'
import { ELEVATION_PROFILE, ROUTE_HOTSPOTS, ROUTE_LENGTH } from '../data/geo'
import { riskColor } from '../data/hotspots'

const W = 320
const H = 104
const PAD = { top: 10, bottom: 18 }

const minE = Math.min(...ELEVATION_PROFILE.map((p) => p.e))
const maxE = Math.max(...ELEVATION_PROFILE.map((p) => p.e))
const x = (d: number) => (d / ROUTE_LENGTH) * W
const y = (e: number) => PAD.top + (1 - (e - (minE - 0.4)) / (maxE - minE + 0.8)) * (H - PAD.top - PAD.bottom)

const line = ELEVATION_PROFILE.map((p, i) => `${i ? 'L' : 'M'}${x(p.d).toFixed(1)},${y(p.e).toFixed(1)}`).join('')
const ground = `${line}L${W},${H}L0,${H}Z`

function elevationAt(d: number) {
  const i = Math.round((d / ROUTE_LENGTH) * (ELEVATION_PROFILE.length - 1))
  return ELEVATION_PROFILE[Math.max(0, Math.min(ELEVATION_PROFILE.length - 1, i))].e
}

/** Route elevation with a water line that rises with rainfall. */
export function ElevationProfile({ rain, selectedId, onSelect }: { rain: number; selectedId: string; onSelect: (id: string) => void }) {
  const reduced = useReducedMotion()
  const waterE = minE + Math.min(2.4, (rain / 100) * 1.7)
  const waterY = y(waterE)

  return (
    <svg className="profile" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Elevation along the route with predicted water level">
      <defs>
        <linearGradient id="ground-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2a2c31" />
          <stop offset="100%" stopColor="#141516" />
        </linearGradient>
        <linearGradient id="water-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4c9aff" stopOpacity="0.75" />
          <stop offset="100%" stopColor="#4c9aff" stopOpacity="0.25" />
        </linearGradient>
      </defs>
      <motion.rect
        x={0}
        width={W}
        height={H}
        fill="url(#water-fill)"
        initial={false}
        animate={{ y: waterY }}
        transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 80, damping: 18 }}
      />
      <path d={ground} fill="url(#ground-fill)" />
      <path d={line} fill="none" stroke="#8a8f98" strokeWidth={1.5} />
      {ROUTE_HOTSPOTS.map(({ hotspot, at }) => (
        <g key={hotspot.id} className="profile-pin" onClick={() => onSelect(hotspot.id)}>
          <line x1={x(at)} x2={x(at)} y1={y(elevationAt(at)) + 4} y2={H - PAD.bottom + 4} stroke={riskColor(hotspot.score)} strokeOpacity={0.5} strokeDasharray="2 3" />
          <circle cx={x(at)} cy={y(elevationAt(at))} r={hotspot.id === selectedId ? 5.5 : 4} fill={riskColor(hotspot.score)} stroke="#0f1011" strokeWidth={2} />
        </g>
      ))}
      <text x={0} y={H - 3} className="profile-axis">0 km</text>
      <text x={W} y={H - 3} textAnchor="end" className="profile-axis">
        {(ROUTE_LENGTH / 1000).toFixed(1)} km
      </text>
    </svg>
  )
}
