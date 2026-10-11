import { motion, useReducedMotion } from 'motion/react'
import { depthAt, segmentLabel } from '../data/analysis'
import type { Analysis } from '../data/analysis'
import { riskColor } from '../data/hotspots'

const W = 320
const H = 120
const PAD = { top: 10, bottom: 22, left: 2, right: 26 }
const MAX_CM = 40
const GAP = 1.5
const SEGMENT_GAP = 10

/**
 * Predicted standing water on every measured stretch at the current rain rate.
 * One bar per ~60 m stretch, in drive order, grouped by survey area. Click a bar to select it.
 */
export function WaterChart({
  analysis,
  rain,
  selectedId,
  onSelect,
}: {
  analysis: Analysis
  rain: number
  selectedId: string
  onSelect: (id: string) => void
}) {
  const reduced = useReducedMotion()
  const segments = [...new Set(analysis.cells.map((c) => c.segment))]
  const groups = segments.map((s) => analysis.cells.filter((c) => c.segment === s).sort((a, b) => a.startM - b.startM))
  const n = analysis.cells.length
  const plotW = W - PAD.left - PAD.right - SEGMENT_GAP * (segments.length - 1)
  const barW = plotW / n - GAP
  const plotH = H - PAD.top - PAD.bottom
  const y = (cm: number) => PAD.top + plotH * (1 - Math.min(cm, MAX_CM) / MAX_CM)

  let x = PAD.left
  const bars = groups.flatMap((cells, gi) => {
    const start = x
    const out = cells.map((c) => {
      const depth = depthAt(c.water, rain)
      const bx = x
      x += barW + GAP
      return { c, depth, x: bx }
    })
    const end = x - GAP
    x += SEGMENT_GAP
    return out.map((b) => ({ ...b, group: gi, groupStart: start, groupEnd: end }))
  })
  const flooded = bars.filter((b) => b.depth >= 15).length

  return (
    <div className="water-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Predicted water on ${n} measured stretches at ${rain} mm per hour; ${flooded} at 15 cm or more`}>
        {[15, 30].map((cm) => (
          <g key={cm}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(cm)} y2={y(cm)} className={'wc-guide' + (cm === 30 ? ' unsafe' : '')} />
            <text x={W - PAD.right + 4} y={y(cm) + 3} className="wc-axis">
              {cm} cm
            </text>
          </g>
        ))}
        <line x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} className="wc-base" />
        {bars.map(({ c, depth, x: bx }) => {
          const h = Math.max(1, y(0) - y(depth))
          return (
            <motion.rect
              key={c.id}
              x={bx}
              width={barW}
              rx={1}
              initial={false}
              animate={{ y: y(0) - h, height: h }}
              transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 120, damping: 20 }}
              fill={riskColor(Math.min(100, (depth / 30) * 100))}
              className={'wc-bar' + (c.id === selectedId ? ' is-selected' : '')}
              onClick={() => onSelect(c.id)}
            >
              <title>{`${c.id}: ${depth.toFixed(1)} cm at ${rain} mm/hr`}</title>
            </motion.rect>
          )
        })}
        {groups.map((cells, gi) => {
          const g = bars.find((b) => b.group === gi)!
          return (
            <text key={gi} x={(g.groupStart + g.groupEnd) / 2} y={H - 6} textAnchor="middle" className="wc-axis">
              {segmentLabel(analysis, cells[0].segment).replace(' approach', '')}
            </text>
          )
        })}
      </svg>
      <span className="wc-summary">
        At <b className="mono">{rain} mm/hr</b>: <b className="mono">{flooded}</b> of {n} stretches have 15 cm of water or more
      </span>
    </div>
  )
}
