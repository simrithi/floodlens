import { AnimatePresence, motion } from 'motion/react'
import type { Variants } from 'motion/react'
import { ArrowsDownUp, CloudRain, NavigationArrow, Path, UploadSimple, VideoCamera } from '@phosphor-icons/react'
import { Logo } from '../ui/Logo'
import { AnimatedNumber } from '../ui/AnimatedNumber'
import { ElevationProfile } from './ElevationProfile'
import { CellDetail, HotspotDetail } from './details'
import { RAIN_PRESETS, RISK_COLORS, riskColor, waterLevel } from '../data/hotspots'
import { ROUTE_HOTSPOTS, ROUTE_LENGTH, ROUTE_NAME } from '../data/geo'
import { RUNS, segmentLabel } from '../data/analysis'
import { useAppState, useSelectedCell, useSelectedHotspot } from '../state'
import './dashboard.css'

const ease = [0.16, 1, 0.3, 1] as const

const panel = (dir: 'left' | 'right' | 'up' | 'down', order: number): Variants => {
  const offset = { left: { x: -40 }, right: { x: 40 }, up: { y: -24 }, down: { y: 32 } }[dir]
  return {
    hidden: { opacity: 0, ...offset, filter: 'blur(8px)' },
    show: {
      opacity: 1,
      x: 0,
      y: 0,
      filter: 'blur(0px)',
      transition: { type: 'spring', stiffness: 110, damping: 22, delay: 1.0 + order * 0.09 },
    },
    exit: { opacity: 0, ...offset, filter: 'blur(8px)', transition: { duration: 0.4, ease } },
  }
}

export function Dashboard({ onHome }: { onHome: () => void }) {
  const { rain, setRain, selectedId, setSelectedId, analysis, analysisStatus, run, setRun } = useAppState()
  const hotspot = useSelectedHotspot()
  const cell = useSelectedCell()
  const routeMinutes = Math.round((ROUTE_LENGTH / 1000 / 28) * 60)
  const measured = analysis ? [...analysis.cells].sort((a, b) => b.risk - a.risk).slice(0, 4) : []

  return (
    <motion.div className="dash" initial="hidden" animate="show" exit="exit">
      {/* Top bar */}
      <motion.header className="dash-top glass" variants={panel('up', 0)}>
        <Logo onClick={onHome} />
        <div className="dash-route-chip">
          <NavigationArrow size={14} weight="fill" />
          <span>{ROUTE_NAME.from}</span>
          <span className="muted">to</span>
          <span>{ROUTE_NAME.to}</span>
        </div>
        <div className="dash-top-right">
          <span className="rain-readout">
            <CloudRain size={16} />
            <span className="mono">
              <AnimatedNumber value={rain} /> mm/hr
            </span>
          </span>
          <button className="btn btn-primary">
            <UploadSimple size={16} weight="bold" />
            Upload footage
          </button>
        </div>
      </motion.header>

      {/* Left: route */}
      <motion.aside className="dash-left glass" variants={panel('left', 1)}>
        <div className="section">
          <h2 className="panel-title">
            <Path size={18} /> Route risk
          </h2>
          <div className="route-stats">
            <div>
              <span className="big mono">{(ROUTE_LENGTH / 1000).toFixed(1)}</span>
              <span className="unit">km</span>
            </div>
            <div>
              <span className="big mono">{routeMinutes}</span>
              <span className="unit">min</span>
            </div>
            <div>
              <span className="big mono" style={{ color: RISK_COLORS[4] }}>
                {ROUTE_HOTSPOTS.length}
              </span>
              <span className="unit">hotspots</span>
            </div>
          </div>
        </div>

        <div className="section">
          <div className="row-between">
            <span className="label">Elevation and water line</span>
            <span className="label mono">
              <AnimatedNumber value={Math.min(2.4, (rain / 100) * 1.7)} decimals={1} /> m
            </span>
          </div>
          <ElevationProfile rain={rain} selectedId={selectedId} onSelect={setSelectedId} />
        </div>

        <div className="section">
          <div className="row-between">
            <span className="label">
              <VideoCamera size={14} /> Measured with dashcam
            </span>
            <div className="seg-toggle" role="group" aria-label="Dashcam analysis resolution">
              {RUNS.map((r) => (
                <button key={r.id} className={run === r.id ? 'is-active' : ''} onClick={() => setRun(r.id)}>
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          {analysisStatus === 'missing' ? (
            <p className="empty">No pipeline output found. Run backend/run_local.py to measure real roads.</p>
          ) : analysisStatus === 'loading' && !analysis ? (
            <ul className="route-list" aria-busy="true">
              {[0, 1, 2].map((i) => (
                <li key={i} className="skeleton-row" />
              ))}
            </ul>
          ) : (
            <ul className="route-list">
              {measured.map((c) => (
                <li key={c.id}>
                  <button className={'route-item' + (c.id === selectedId ? ' is-selected' : '')} onClick={() => setSelectedId(c.id)}>
                    <span className="route-score mono" style={{ color: riskColor(c.risk) }}>
                      {c.risk}
                    </span>
                    <span className="route-text">
                      <span className="route-name">{segmentLabel(analysis!, c.segment)}</span>
                      <span className="route-meta">
                        {c.id}, {c.maxDipCm ? `dip ${c.maxDipCm.toFixed(0)} cm` : 'no dips'}, {c.demRelativeM.toFixed(1)} m vs. around
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="section">
          <span className="label">Along this route (sample)</span>
          <ul className="route-list">
            {ROUTE_HOTSPOTS.map(({ hotspot: h, at }) => (
              <li key={h.id}>
                <button className={'route-item' + (h.id === selectedId ? ' is-selected' : '')} onClick={() => setSelectedId(h.id)}>
                  <span className="route-score mono" style={{ color: riskColor(h.score) }}>
                    {h.score}
                  </span>
                  <span className="route-text">
                    <span className="route-name">{h.name}</span>
                    <span className="route-meta">
                      {(at / 1000).toFixed(1)} km in, {waterLevel(h, rain)} cm water
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="safer">
          <ArrowsDownUp size={16} />
          <span>
            Safer route via Mathura Road avoids 2 hotspots, <b>+4 min</b>
          </span>
        </div>
      </motion.aside>

      {/* Right: selected hotspot or measured stretch */}
      <motion.aside className="dash-right glass" variants={panel('right', 2)}>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.div
            key={selectedId + run}
            className="detail"
            initial={{ opacity: 0, y: 14, filter: 'blur(6px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -10, filter: 'blur(6px)' }}
            transition={{ duration: 0.35, ease }}
          >
            {cell ? <CellDetail cell={cell} /> : hotspot ? <HotspotDetail hotspot={hotspot} /> : null}
          </motion.div>
        </AnimatePresence>
      </motion.aside>

      {/* Bottom: rain simulator */}
      <motion.footer className="dash-rain glass" variants={panel('down', 3)}>
        <span className="rain-title">
          <CloudRain size={18} weight="fill" />
          Rain simulator
        </span>
        <input
          className="rain-slider"
          type="range"
          min={0}
          max={150}
          value={rain}
          style={{ ['--p' as string]: `${(rain / 150) * 100}%` }}
          onChange={(e) => setRain(Number(e.target.value))}
          aria-label="Rainfall intensity in millimetres per hour"
        />
        <div className="presets" role="group" aria-label="Rain presets">
          {RAIN_PRESETS.map((p) => (
            <button key={p.label} className={'preset' + (rain === p.value ? ' is-active' : '')} onClick={() => setRain(p.value)}>
              {p.label}
            </button>
          ))}
        </div>
      </motion.footer>

      <motion.div className="dash-legend glass" variants={panel('down', 4)}>
        <span className="legend-bar" style={{ background: `linear-gradient(90deg, ${RISK_COLORS.join(', ')})` }} />
        <span className="legend-labels">
          <span>Drains</span>
          <span>Floods</span>
        </span>
        <span className="legend-note">
          <span className="legend-swatch measured" /> Measured
          <span className="legend-swatch sample" /> Sample
        </span>
      </motion.div>
    </motion.div>
  )
}
