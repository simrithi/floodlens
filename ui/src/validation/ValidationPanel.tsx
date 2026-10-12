import { useEffect } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ArrowSquareOut, CheckCircle, Info, X, XCircle } from '@phosphor-icons/react'
import type { CellCheck, Validation } from '../data/validation'
import { useAppState } from '../state'
import './validation.css'

const pct = (v: number | null | undefined) => (v === null || v === undefined ? 'n/a' : `${Math.round(v * 100)}%`)

function topDistances(c: CellCheck) {
  const d = [...c.perCell].sort((a, b) => b.risk - a.risk).slice(0, 5).map((x) => x.distanceM)
  const lo = Math.min(...d)
  const hi = Math.max(...d)
  return lo === hi ? `${lo} m` : `${lo} to ${hi} m`
}

/** Dot strip: each reported hotspot and each control road point by height vs. the surrounding 400 m. */
function StripPlot({ v }: { v: Validation }) {
  const t = v.terrain
  const lo = -8
  const hi = 6
  const W = 560
  const x = (m: number) => ((Math.min(hi, Math.max(lo, m)) - lo) / (hi - lo)) * W
  const jitter = (i: number) => ((i * 7919) % 17) - 8
  const ticks = [-8, -6, -4, -2, 0, 2, 4, 6]
  return (
    <svg className="strip" viewBox={`-84 0 ${W + 100} 132`} role="img" aria-label="Height relative to surroundings: reported hotspots versus ordinary main roads">
      <rect x={x(lo)} y={8} width={x(t.lowGroundThresholdM) - x(lo)} height={100} className="strip-zone" />
      <text x={x(lo) + 6} y={20} className="strip-zone-label">
        Low ground (≤ {t.lowGroundThresholdM} m)
      </text>
      <text x={-8} y={46} textAnchor="end" className="strip-label">
        Reported
      </text>
      <text x={-8} y={92} textAnchor="end" className="strip-label">
        Main roads
      </text>
      {t.perHotspot.map((h, i) => (
        <circle key={h.id} cx={x(h.relativeM)} cy={42 + jitter(i) * 0.9} r={4} className="dot-hot">
          <title>{`${h.name}: ${h.relativeM > 0 ? '+' : ''}${h.relativeM} m`}</title>
        </circle>
      ))}
      {t.controlsRelativeM.map((m, i) => (
        <circle key={i} cx={x(m)} cy={88 + jitter(i) * 1.1} r={2.2} className="dot-ctrl" />
      ))}
      <line x1={x(t.medianRelativeHotspotsM)} x2={x(t.medianRelativeHotspotsM)} y1={28} y2={58} className="median hot" />
      <line x1={x(t.medianRelativeControlsM)} x2={x(t.medianRelativeControlsM)} y1={72} y2={104} className="median ctrl" />
      {ticks.map((m) => (
        <g key={m}>
          <line x1={x(m)} x2={x(m)} y1={108} y2={112} className="tick" />
          <text x={x(m)} y={126} textAnchor="middle" className="strip-axis">
            {m > 0 ? `+${m}` : m} m
          </text>
        </g>
      ))}
    </svg>
  )
}

export function ValidationPanel() {
  const { validation: v, setShowValidation, run } = useAppState()
  const reduced = useReducedMotion()
  const close = () => setShowValidation(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setShowValidation(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setShowValidation])

  if (!v) return null
  const t = v.terrain
  const c = v.cells[run]
  const significant = t.aucCi95[0] > 0.5

  return (
    <motion.div className="val-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={close}>
      <motion.section
        className="val"
        role="dialog"
        aria-modal="true"
        aria-labelledby="val-title"
        onClick={(e) => e.stopPropagation()}
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 12, scale: 0.98 }}
        transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 170, damping: 24 }}
      >
        <header className="val-head">
          <div>
            <h2 id="val-title">How accurate is Varshik?</h2>
            <p>Checked against {v.reference.count} publicly reported Delhi waterlogging hotspots.</p>
          </div>
          <button className="sv-close" onClick={close} aria-label="Close">
            <X size={18} />
          </button>
        </header>

        <div className="val-body">
          <section className="val-block">
            <h3>Terrain check, city-wide (bare earth)</h3>
            <p className="val-q">Do reported hotspots sit lower than ordinary main roads?</p>
            <div className="val-stats">
              <div>
                <span className="val-big mono">{pct(t.hitRate)}</span>
                <span className="val-cap">of reported hotspots are on low ground</span>
              </div>
              <div>
                <span className="val-big mono muted-num">{pct(t.controlRate)}</span>
                <span className="val-cap">of {t.controls} random main-road points are</span>
              </div>
              <div>
                <span className="val-big mono">{t.auc.toFixed(2)}</span>
                <span className="val-cap">
                  AUC (0.5 = chance), 95% CI {t.aucCi95[0].toFixed(2)} to {t.aucCi95[1].toFixed(2)}
                </span>
              </div>
            </div>
            <StripPlot v={v} />
            <p className={'val-verdict ' + (significant ? 'ok' : 'warn')}>
              {significant ? <CheckCircle size={16} weight="fill" /> : <Info size={16} weight="fill" />}
              {significant
                ? 'Reported hotspots sit measurably lower than ordinary roads.'
                : `Hotspots sit a little lower on average (median ${t.medianRelativeHotspotsM} m vs ${t.medianRelativeControlsM} m), but terrain alone does not reliably separate them from ordinary roads. Water-flow and drainage data are needed.`}
            </p>
          </section>

          <section className="val-block">
            <h3>Water-flow features, city-wide</h3>
            <p className="val-q">
              Computed on bare-earth elevation (FABDEM) and OpenStreetMap drains, within {v.hydrology.radiusM} m of each point.
            </p>
            <div className="val-table feature-table" role="table" aria-label="Water-flow features">
              {Object.entries(v.hydrology.features).map(([k, f]) => {
                const sig = f.aucCi95[0] > 0.5
                return (
                  <div key={k} className="val-row" role="row">
                    <span role="cell" className="val-name">{f.label}</span>
                    <span role="cell" className="mono val-rel">{f.auc.toFixed(2)}</span>
                    <span role="cell" className="mono val-ci">
                      {f.aucCi95[0].toFixed(2)} to {f.aucCi95[1].toFixed(2)}
                    </span>
                    <span role="cell" className={'val-hit ' + (sig ? 'yes' : 'no')}>
                      {sig ? <CheckCircle size={15} weight="fill" /> : <XCircle size={15} />}
                      {sig ? 'Beats chance' : 'Not shown'}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="val-verdict warn">
              <Info size={16} weight="fill" />
              Only "sits in a hollow" separates reported hotspots from ordinary roads beyond chance. Underpasses are narrower than the
              30 m elevation grid, which is why the dashcam's dip measurements matter. Surface model for comparison: AUC{' '}
              {v.terrainSurface.auc.toFixed(2)} vs {t.auc.toFixed(2)} on bare earth.
            </p>
          </section>

          <section className="val-block">
            <h3>Dashcam stretches</h3>
            {c ? (
              <>
                <p className="val-q">
                  Are measured stretches within {c.nearRadiusM} m of a reported hotspot scored higher?
                </p>
                <div className="val-stats">
                  <div>
                    <span className="val-big mono">
                      {c.cellsNearHotspot}/{c.cells}
                    </span>
                    <span className="val-cap">stretches near {c.hotspotsCovered.map((h) => h.name).join(', ') || 'no reported hotspot'}</span>
                  </div>
                  <div>
                    <span className="val-big mono">
                      {c.meanRiskNear ?? 'n/a'} <span className="vs">vs</span> {c.meanRiskOther ?? 'n/a'}
                    </span>
                    <span className="val-cap">mean risk, near vs. other stretches</span>
                  </div>
                  <div>
                    <span className="val-big mono">{c.precisionTop5 !== null ? `${Math.round(c.precisionTop5 * 5)}/5` : 'n/a'}</span>
                    <span className="val-cap">of our 5 riskiest stretches are near a reported hotspot</span>
                  </div>
                </div>
                <p className="val-verdict warn">
                  <Info size={16} weight="fill" />
                  Inconclusive: the drive covers about 2.5 km and only {c.hotspotsCovered.length} reported hotspot
                  {c.hotspotsCovered.length === 1 ? ' is' : 's are'} within {c.nearRadiusM} m. The stretches near it are a flat approach with no
                  dips; our 5 riskiest stretches are {topDistances(c)} from the nearest reported hotspot, beyond the test radius.
                </p>
              </>
            ) : (
              <p className="val-q">No pipeline output for this run.</p>
            )}
          </section>

          <section className="val-block">
            <h3>Every reported hotspot</h3>
            <div className="val-table" role="table" aria-label="Reported hotspots">
              {t.perHotspot.map((h) => {
                const ref = v.reference.points.find((p) => p.id === h.id)
                return (
                  <div key={h.id} className="val-row" role="row">
                    <span role="cell" className="val-name">
                      {h.name}
                      {ref?.approximate && <span className="tag tag-sample">approx. location</span>}
                    </span>
                    <span role="cell" className="mono val-rel">
                      {h.relativeM > 0 ? '+' : ''}
                      {h.relativeM.toFixed(1)} m
                    </span>
                    <span role="cell" className={'val-hit ' + (h.lowGround ? 'yes' : 'no')}>
                      {h.lowGround ? <CheckCircle size={15} weight="fill" /> : <XCircle size={15} />}
                      {h.lowGround ? 'Low ground' : 'Missed'}
                    </span>
                    <span role="cell" className="val-src">
                      {ref?.sources.map((s) => (
                        <a key={s} href={v.reference.sources[s]?.url} target="_blank" rel="noreferrer" title={v.reference.sources[s]?.title}>
                          {v.reference.sources[s]?.kind === 'official' ? 'Official' : 'Report'}
                          <ArrowSquareOut size={11} />
                        </a>
                      ))}
                    </span>
                  </div>
                )
              })}
            </div>
          </section>

          <section className="val-block">
            <h3>Limits of this check</h3>
            <ul className="val-caveats">
              {v.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </section>
        </div>
      </motion.section>
    </motion.div>
  )
}
