import { useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Brain, CarProfile, CheckCircle, Cloud, Cpu, Database, Eye, FileText, GlobeHemisphereEast, Mountains, Ruler, Stack, Waves, Wrench, X } from '@phosphor-icons/react'
import type { Icon } from '@phosphor-icons/react'
import { outputUrl } from '../data/findings'
import { useAppState } from '../state'
import './how.css'

const ease = [0.16, 1, 0.3, 1] as const

type Stage = { id: string; icon: Icon; title: string; short: string; body: string; tech: string[] }

const STAGES: Stage[] = [
  {
    id: 'capture',
    icon: CarProfile,
    title: 'Capture',
    short: 'An ordinary dashcam drive',
    body: 'Any phone on a dashboard records video, GPS and its own tilt. We use public KartaView drives: no new survey, no special hardware.',
    tech: ['KartaView open imagery (CC BY-SA)', 'GPS 1 Hz', 'Gravity sensor ~10 Hz'],
  },
  {
    id: 'see',
    icon: Eye,
    title: 'See the road',
    short: 'AI reads every frame',
    body: 'Each frame is split into road, footpath, kerb and vehicles, turned into a depth map, then fitted with the road’s own curved surface. Anything below that surface is a dip; road edges become kerb lines; potholes count only if they are measurably lower.',
    tech: ['SegFormer-B2 (Cityscapes) segmentation', 'Depth Anything V2 depth', 'YOLOv8m-seg potholes', 'Curved road-surface fit'],
  },
  {
    id: 'feel',
    icon: Ruler,
    title: 'Feel the road',
    short: 'The phone feels every dip',
    body: 'As the car goes down into an underpass, the phone tilts. Tilt times distance gives the road’s height profile, to fractions of a metre. Satellites cannot see an underpass; the car can.',
    tech: ['Gravity-vector road grade', 'Braking correction from GPS speed', 'Sag = depth below the lower rim'],
  },
  {
    id: 'land',
    icon: Mountains,
    title: 'Know the land',
    short: 'Where rain runs to',
    body: 'Bare-earth elevation shows the hollows and how much land drains to each point. The official storm-drain map shows where drains exist, and the city drainage plans give the storms to plan for.',
    tech: ['FABDEM bare earth 30 m', 'Copernicus DEM (AWS Open Data)', 'pysheds flow routing', 'Official storm-drain map (KSRSAC 2022)', 'BBMP 2010 / IIT Delhi design storms'],
  },
  {
    id: 'fix',
    icon: Wrench,
    title: 'Predict and fix',
    short: 'Depth, cause, and the fix size',
    body: 'A water balance for every 60 m of road predicts standing water in 2, 5 and 10-year storms. Run backwards, it gives the drainage in litres per second that keeps the road passable, so officials get a cause, a sized fix and a priority.',
    tech: ['Water balance per 60 m stretch', 'Cause diagnosis', 'Drainage needed (L/s)', 'PDF report per city'],
  },
]

const FRAME_VIEWS = [
  { id: 'image', label: 'Dashcam frame', note: 'What the phone recorded' },
  { id: 'overlay', label: 'AI findings', note: 'Road edges, kerbs, dips found by the models' },
  { id: 'depth', label: 'AI depth', note: 'Depth Anything V2: near is warm, far is cool' },
] as const

const STACK: { icon: Icon; group: string; items: string[]; planned?: boolean }[] = [
  { icon: Brain, group: 'AI models', items: ['SegFormer-B2 (NVIDIA, Cityscapes)', 'Depth Anything V2 Small', 'YOLOv8m-seg pothole model', 'PyTorch 2 on CUDA'] },
  { icon: Database, group: 'Open data', items: ['KartaView street imagery', 'Official BBMP storm-drain map (KSRSAC 2022)', 'BBMP drain master plan storms (IMD)', 'FABDEM bare-earth DEM', 'Copernicus DEM (AWS Registry of Open Data)', 'OpenStreetMap roads and Delhi drains'] },
  { icon: Cpu, group: 'Pipeline', items: ['Python 3.12', 'Hugging Face transformers', 'Ultralytics', 'OpenCV', 'rasterio', 'pysheds', 'SciPy'] },
  { icon: Stack, group: 'App', items: ['React 19', 'TypeScript', 'Vite', 'MapLibre GL 3D map', 'Motion animations'] },
  { icon: Cloud, group: 'AWS', items: ['S3 + CloudFront hosting', 'Bedrock (Claude) report writing', 'Lambda + EventBridge forecast alerts', 'SNS notifications'], planned: true },
]

export function HowItWorks({ onClose }: { onClose: () => void }) {
  const reduced = useReducedMotion() ?? false
  const { findings } = useAppState()
  const [stage, setStage] = useState(0)
  const [auto, setAuto] = useState(true)
  const [view, setView] = useState(0)

  // Walk through the stages until the user picks one.
  useEffect(() => {
    if (!auto || reduced) return
    const t = window.setInterval(() => setStage((s) => (s + 1) % STAGES.length), 4200)
    return () => window.clearInterval(t)
  }, [auto, reduced])
  useEffect(() => {
    if (reduced) return
    const t = window.setInterval(() => setView((v) => (v + 1) % FRAME_VIEWS.length), 3200)
    return () => window.clearInterval(t)
  }, [reduced])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Worked example: the best-evidenced sag spot of the current city, else the first spot.
  const spot = findings?.spots.find((s) => s.cause === 'sag' && s.reported) ?? findings?.spots[0] ?? null
  const z = spot?.sizing
  const volume = z ? (0.85 * Math.max(0, z.rainMmHr - z.designMmHr) * 0.25 * z.areaM2) / 1000 : 0
  const frame = spot?.frame
  const framePaths = frame && { image: frame.image, overlay: frame.overlay, depth: frame.overlay.replace('/overlays/', '/depth/') }
  const frameSrc = framePaths ? outputUrl(framePaths[FRAME_VIEWS[view].id]) : null
  const S = STAGES[stage]

  return (
    <motion.div className="how-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div
        className="how"
        role="dialog"
        aria-modal="true"
        aria-labelledby="how-title"
        onClick={(e) => e.stopPropagation()}
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.98 }}
        transition={{ duration: 0.45, ease }}
      >
        <header className="how-head">
          <div>
            <span className="label mono">How it works</span>
            <h2 id="how-title">From a dashcam drive to a sized fix</h2>
            <p>FloodLens finds the roads that will flood before the monsoon, explains why, and tells officials how much drainage each one needs.</p>
          </div>
          <button className="how-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>

        <div className="how-body">
          {/* 1. Pipeline */}
          <section>
            <h3 className="how-h">
              <span className="how-num">1</span> Five steps, fully automatic
            </h3>
            <div className="pipe">
              <div className="pipe-line" aria-hidden="true">
                <span className="pipe-flow" />
                {!reduced && (
                  <motion.span
                    className="pipe-drop"
                    animate={{ left: `${(stage / (STAGES.length - 1)) * 100}%` }}
                    transition={{ type: 'spring', stiffness: 70, damping: 16 }}
                  />
                )}
              </div>
              {STAGES.map((st, i) => {
                const I = st.icon
                return (
                  <motion.button
                    key={st.id}
                    className={'pipe-stage' + (i === stage ? ' is-active' : '') + (i < stage ? ' is-done' : '')}
                    onClick={() => {
                      setStage(i)
                      setAuto(false)
                    }}
                    initial={{ opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.15 + i * 0.08, duration: 0.5, ease }}
                  >
                    <span className="pipe-icon">
                      <I size={20} weight="duotone" />
                    </span>
                    <span className="pipe-title">{st.title}</span>
                    <span className="pipe-short">{st.short}</span>
                  </motion.button>
                )
              })}
            </div>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={S.id}
                className="pipe-detail"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.3, ease }}
              >
                <p>{S.body}</p>
                <div className="chips">
                  {S.tech.map((t) => (
                    <span key={t} className="chip">
                      {t}
                    </span>
                  ))}
                </div>
              </motion.div>
            </AnimatePresence>
          </section>

          <div className="how-grid">
            {/* 2. Real frame */}
            {frame && frameSrc && (
              <section>
                <h3 className="how-h">
                  <span className="how-num">2</span> What the AI sees, on a real frame
                </h3>
                <div className="frame-box">
                  <AnimatePresence initial={false}>
                    <motion.img
                      key={frameSrc}
                      src={frameSrc}
                      alt={FRAME_VIEWS[view].note}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.6 }}
                    />
                  </AnimatePresence>
                  <span className="frame-tag">{spot?.name}</span>
                </div>
                <div className="seg-toggle frame-tabs" role="tablist">
                  {FRAME_VIEWS.map((v, i) => (
                    <button key={v.id} role="tab" aria-selected={i === view} className={i === view ? 'is-active' : ''} onClick={() => setView(i)}>
                      {v.label}
                    </button>
                  ))}
                </div>
                <p className="how-note">{FRAME_VIEWS[view].note}</p>
              </section>
            )}

            {/* 3. Worked example */}
            {spot && z && z.requiredLs != null && (
              <section>
                <h3 className="how-h">
                  <span className="how-num">3</span> The water maths, at {spot.name}
                </h3>
                <ol className="maths">
                  {[
                    { k: 'Storm that comes every 2 years', v: `${z.rainMmHr.toFixed(0)} mm/hr`, d: `${spot.station} rain gauge, 15-minute burst` },
                    z.designMmHr > 0
                      ? { k: 'Drains built to the city standard take', v: `${z.designMmHr.toFixed(0)} mm/hr`, d: findings?.drainStandard ?? 'Documented design standard' }
                      : { k: 'Storm drain at this spot', v: 'none', d: `Official drain map: nearest drain ${spot.drain.distanceM} m away` },
                    { k: 'Runoff that collects', v: `${Math.round(volume)} m³`, d: `85% of the rain${z.designMmHr > 0 ? ' the drains cannot take' : ''}, for 15 min, over ${z.areaM2.toLocaleString('en-IN')} m² draining here` },
                    { k: 'Standing water at the low point', v: `${spot.depthCm['2'].toFixed(0)} cm`, d: 'Poured into the road profile the phone measured' },
                    { k: 'Drainage needed for under 5 cm', v: `${z.requiredLs} L/s`, d: 'From the storm and the measured ground only' },
                  ].map((r, i) => (
                    <motion.li
                      key={r.k}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.4 + i * 0.12, duration: 0.45, ease }}
                      className={i === 4 ? 'is-result' : ''}
                    >
                      <span className="maths-k">{r.k}</span>
                      <span className="maths-v mono">{r.v}</span>
                      <span className="maths-d">{r.d}</span>
                    </motion.li>
                  ))}
                </ol>
              </section>
            )}
          </div>

          {/* 4. Stack */}
          <section>
            <h3 className="how-h">
              <span className="how-num">4</span> Built with
            </h3>
            <div className="stack">
              {STACK.map((g, i) => {
                const I = g.icon
                return (
                  <motion.div
                    key={g.group}
                    className="stack-card"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 + i * 0.07, duration: 0.45, ease }}
                  >
                    <span className="stack-head">
                      <I size={16} weight="duotone" /> {g.group}
                      {g.planned && <span className="tag tag-sample">Deployment</span>}
                    </span>
                    <ul>
                      {g.items.map((t) => (
                        <li key={t}>{t}</li>
                      ))}
                    </ul>
                  </motion.div>
                )
              })}
            </div>
          </section>

          {/* 5. Checks */}
          <section>
            <h3 className="how-h">
              <span className="how-num">5</span> How we checked it
            </h3>
            <div className="checks">
              {[
                { icon: Waves, big: '0.69', unit: 'AUC', text: 'Phone road profile picks out mapped underpasses along 45 km of Bengaluru road. Satellite elevation alone: 0.47 (chance).' },
                { icon: CheckCircle, big: '2 / 2', unit: 'passes', text: 'The Kadubeesanahalli underpass is flagged on both driving directions and was reported waterlogged by traffic police in June 2023.' },
                { icon: Ruler, big: '11 / 11', unit: 'frames', text: 'Synthetic 8 cm dips planted in real frames are all found; 3 cm ones are not, by design.' },
                { icon: GlobeHemisphereEast, big: '0.66', unit: 'AUC', text: 'Delhi: predicted water depth at 36 publicly reported hotspots vs 400 random main-road points (95% CI 0.60 to 0.72).' },
              ].map((c) => {
                const I = c.icon
                return (
                  <div key={c.text} className="check">
                    <I size={18} weight="duotone" />
                    <span className="check-big mono">
                      {c.big} <small>{c.unit}</small>
                    </span>
                    <p>{c.text}</p>
                  </div>
                )
              })}
            </div>
            <p className="how-note">
              <FileText size={12} /> A screening tool: today's real drain capacity is not published, so drains are credited only with their documented design standard; a single sag is a lead to check on the ground, not proof.
            </p>
          </section>
        </div>
      </motion.div>
    </motion.div>
  )
}
