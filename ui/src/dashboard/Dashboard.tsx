import { AnimatePresence, motion } from 'motion/react'
import type { Variants } from 'motion/react'
import { useState } from 'react'
import { CloudRain, FilePdf, Path, PlayCircle, Sparkle, Target, Wrench } from '@phosphor-icons/react'
import { Logo } from '../ui/Logo'
import { SurveyPicker } from './SurveyPicker'
import { Tour } from '../tour/Tour'
import { PriorityList } from './spots'
import { HowItWorks } from '../how/HowItWorks'
import { WaterChart } from './WaterChart'
import { LayerPanel } from './LayerPanel'
import { CellDetail, HotspotDetail } from './details'
import { RAIN_PRESETS, RISK_COLORS } from '../data/hotspots'
import { RUNS, filmedKm } from '../data/analysis'
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
  const { rain, setRain, selectedId, setSelectedId, analysis, analysisStatus, survey, run, setRun, validation, setShowValidation, findings } = useAppState()
  const hotspot = useSelectedHotspot()
  const cell = useSelectedCell()
  // Walkthrough for the demo video; ?tour=1 starts it on load.
  const [showHow, setShowHow] = useState(false)
  const [touring, setTouring] = useState(() => new URLSearchParams(window.location.search).has('tour'))

  return (
    <motion.div className="dash" initial="hidden" animate="show" exit="exit">
      {/* Top bar */}
      <motion.header className="dash-top glass" variants={panel('up', 0)}>
        <Logo onClick={onHome} />
        <SurveyPicker />
        <button className="how-btn" onClick={() => setShowHow(true)}>
          <span className="how-dot" aria-hidden="true" />
          <Sparkle size={15} weight="fill" />
          How it works
        </button>
        <div className="dash-top-right">
          <button className={'btn' + (touring ? ' is-open' : '')} onClick={() => setTouring((t) => !t)}>
            <PlayCircle size={16} />
            Walkthrough
          </button>
          <LayerPanel />
          {validation && survey.validation && (
            <button className="btn accuracy-btn" onClick={() => setShowValidation(true)}>
              <Target size={16} />
              Accuracy
              <span className="mono accuracy-auc">AUC {validation.terrain.auc.toFixed(2)}</span>
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={() => window.open(`/report/${survey.city}?print=1`, '_blank', 'noopener')}
            title={`Findings report for ${survey.city === 'delhi' ? 'Delhi' : 'Bengaluru'} (opens the print dialog: choose Save as PDF)`}
          >
            <FilePdf size={16} weight="bold" />
            Export PDF
          </button>
        </div>
      </motion.header>

      {/* Left: route */}
      <motion.aside className="dash-left glass" variants={panel('left', 1)}>
        <div className="section">
          <div className="row-between">
            <h2 className="panel-title">
              <Path size={18} /> Survey
            </h2>
            {survey.runs.length > 1 && (
              <div className="seg-toggle" role="group" aria-label="Dashcam analysis resolution">
                {RUNS.filter((r) => survey.runs.includes(r.id)).map((r) => (
                  <button key={r.id} className={run === r.id ? 'is-active' : ''} onClick={() => setRun(r.id)}>
                    {r.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {analysis ? (
            <div className="route-stats">
              <div>
                <span className="big mono">{filmedKm(analysis).toFixed(1)}</span>
                <span className="unit">km filmed</span>
              </div>
              <div>
                <span className="big mono">{analysis?.cells.length ?? 0}</span>
                <span className="unit">stretches</span>
              </div>
              <div>
                <span className="big mono" style={{ color: RISK_COLORS[3] }}>
                  {findings?.spots.filter((x) => x.sequence === survey.sequence).length ?? 0}
                </span>
                <span className="unit">spots to fix</span>
              </div>
            </div>
          ) : (
            <p className="empty">No pipeline output for this survey yet.</p>
          )}
        </div>

        {analysis && (
          <div className="section">
            <span className="label">Predicted water on each measured stretch</span>
            <WaterChart analysis={analysis} rain={rain} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
        )}

        <div className="section">
          <span className="label">
            <Wrench size={14} /> Where to act first
          </span>
          {analysisStatus === 'missing' ? (
            <p className="empty">No pipeline output found. Run backend/run_local.py to measure real roads.</p>
          ) : findings ? (
            <PriorityList findings={findings} selectedId={selectedId} />
          ) : (
            <ul className="route-list" aria-busy="true">
              {[0, 1, 2].map((i) => (
                <li key={i} className="skeleton-row" />
              ))}
            </ul>
          )}
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

      {touring && <Tour onExit={() => setTouring(false)} />}
      <AnimatePresence>{showHow && <HowItWorks onClose={() => setShowHow(false)} />}</AnimatePresence>

      <motion.div className="dash-legend glass" variants={panel('down', 4)}>
        <span className="legend-bar" style={{ background: `linear-gradient(90deg, ${RISK_COLORS.join(', ')})` }} />
        <span className="legend-labels">
          <span>Drains</span>
          <span>Floods</span>
        </span>
        <span className="legend-note">
          <span className="legend-swatch measured" /> Measured
          <span className="legend-swatch sample" /> Sample
          {validation && survey.validation && (
            <>
              <span className="legend-ring" /> Reported
            </>
          )}
        </span>
      </motion.div>
    </motion.div>
  )
}
