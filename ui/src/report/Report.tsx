import { useEffect, useMemo, useState } from 'react'
import { MotionConfig } from 'motion/react'
import { ArrowLeft, CheckCircle, Drop, FilePdf, Megaphone, Wrench } from '@phosphor-icons/react'
import { loadAnalysis } from '../data/analysis'
import type { Analysis } from '../data/analysis'
import { CAUSE_SHORT, CONFIDENCE, PRIORITY, loadFindings, outputUrl } from '../data/findings'
import type { Findings, Spot } from '../data/findings'
import { FrameCheckResult, useCachedCheck } from '../dashboard/aws-panels'
import { BriefSection } from './Brief'
import { CapacityBars, ProfileChart } from '../dashboard/spots'
import './report.css'

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })

/** Overview map: the surveyed drives and the numbered spots, drawn as a simple vector schematic. */
function OverviewMap({ tracks, spots }: { tracks: [number, number][][]; spots: Spot[] }) {
  const all = [...tracks.flat(), ...spots.map((s) => [s.lng, s.lat] as [number, number])]
  if (!all.length) return null
  const lngs = all.map((p) => p[0])
  const lats = all.map((p) => p[1])
  const pad = 0.08
  const [w0, w1, s0, s1] = [Math.min(...lngs), Math.max(...lngs), Math.min(...lats), Math.max(...lats)]
  const kx = Math.cos((((s0 + s1) / 2) * Math.PI) / 180)
  const spanX = (w1 - w0) * kx || 0.001
  const spanY = s1 - s0 || 0.001
  const W = 600
  const H = Math.max(220, Math.min(420, (W * spanY) / spanX))
  const scale = Math.min(W / (spanX * (1 + 2 * pad)), H / (spanY * (1 + 2 * pad)))
  const cx = (w0 + w1) / 2
  const cy = (s0 + s1) / 2
  const px = (lng: number) => W / 2 + (lng - cx) * kx * scale
  const py = (lat: number) => H / 2 - (lat - cy) * scale
  const metres = 500
  const bar = (metres / 111320) * scale
  return (
    <svg className="rep-map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Surveyed roads and flagged spots">
      {tracks.map((t, i) => (
        <polyline key={i} points={t.map(([x, y]) => `${px(x).toFixed(1)},${py(y).toFixed(1)}`).join(' ')} className="rep-track" />
      ))}
      {spots.map((s) => (
        <g key={s.id} transform={`translate(${px(s.lng)},${py(s.lat)})`}>
          <circle r="13" fill={PRIORITY[s.priority].color} opacity="0.18" />
          <circle r="7" fill={PRIORITY[s.priority].color} />
          <text x="12" y="-10" className="rep-map-label">
            {s.id}
          </text>
        </g>
      ))}
      <g transform={`translate(${W - bar - 16},${H - 16})`}>
        <line x1="0" x2={bar} y1="0" y2="0" stroke="#555" strokeWidth="2" />
        <text x={bar / 2} y="-6" textAnchor="middle" className="rep-map-scale">
          {metres} m
        </text>
      </g>
      <text x="12" y={H - 12} className="rep-map-scale">
        N up
      </text>
    </svg>
  )
}

function SpotSection({ spot, index, city }: { spot: Spot; index: number; city: string }) {
  const p = PRIORITY[spot.priority]
  const [check] = useCachedCheck(city, spot.id)
  return (
    <section className={'rep-spot' + (index > 0 ? ' break' : '')}>
      <header className="rep-spot-head" style={{ ['--c' as string]: p.color }}>
        <span className="rep-spot-id">{spot.id}</span>
        <div>
          <h2>{spot.name}</h2>
          <p>
            {spot.causeLabel}. {spot.lat.toFixed(5)}, {spot.lng.toFixed(5)}
          </p>
        </div>
        <span className="rep-prio">{p.label}</span>
      </header>

      <div className="rep-kpis">
        <div>
          <span>Water in a 2-year storm</span>
          <b>{spot.depthCm['2'].toFixed(0)} cm</b>
          <small>
            5-yr {spot.depthCm['5'].toFixed(0)} cm, 10-yr {spot.depthCm['10'].toFixed(0)} cm
          </small>
        </div>
        <div>
          <span>Drainage needed</span>
          <b>{spot.sizing.requiredLs ?? 'n/a'} L/s</b>
          <small>{spot.drain.distanceM > 30 && spot.evidence.some((e) => e.kind === 'nodrain') ? `no storm drain within ${spot.drain.distanceM} m` : 'to stay under 5 cm'}</small>
        </div>
        <div>
          <span>Confidence</span>
          <b>{CONFIDENCE[spot.confidence].replace(' confidence', '')}</b>
          <small>{(() => { const n = spot.evidence.filter((e) => e.kind !== 'catchment').length; return `${n} independent ${n === 1 ? 'signal' : 'signals'}` })()}</small>
        </div>
      </div>

      <div className="rep-cols">
        <figure className="rep-frame">
          <img src={outputUrl(spot.frame.overlay)} alt={`Dashcam frame ${spot.frame.index} at ${spot.name}`} />
          <figcaption>Dashcam frame {spot.frame.index} with what the models found (road edges, dips).</figcaption>
        </figure>
        <div className="rep-why">
          <h3>
            <Drop size={14} weight="fill" /> Why water collects here
          </h3>
          <p>{spot.why}</p>
          <ul>
            {spot.evidence.map((e) => (
              <li key={e.kind}>{e.text}</li>
            ))}
          </ul>
        </div>
      </div>

      {spot.profile && (
        <div className="rep-profile">
          <h3>Road profile through the spot, with the water of a 2-year storm</h3>
          <ProfileChart profile={spot.profile} waterM={spot.depthCm['2'] / 100} height={200} width={720} />
        </div>
      )}

      <div className="rep-fix">
        <h3>
          <Wrench size={14} weight="fill" /> What fixes it
        </h3>
        <CapacityBars spot={spot} />
        <p>{spot.fix}</p>
        <p className="rep-now">
          <CheckCircle size={14} weight="fill" /> {spot.now}
        </p>
      </div>

      {check && (
        <div className="rep-check">
          <h3>What the dashcam shows</h3>
          <FrameCheckResult check={check} />
        </div>
      )}

      {spot.reported && (
        <p className="rep-reported">
          <Megaphone size={14} weight="fill" /> Publicly reported waterlogged: {spot.reported.name}, {spot.reported.distanceM} m away.
          {spot.reported.source && <> Source: {spot.reported.source}.</>}
        </p>
      )}
      <p className="rep-small">
        Seen on: {spot.directions.join('; ')}. Stretches: {spot.cells.join(', ')}.
      </p>
    </section>
  )
}

export function Report({ city }: { city: string }) {
  const [findings, setFindings] = useState<Findings | null>(null)
  const [tracks, setTracks] = useState<[number, number][][]>([])
  const [error, setError] = useState<string | null>(null)
  const autoPrint = useMemo(() => new URLSearchParams(window.location.search).has('print'), [])

  useEffect(() => {
    const ctrl = new AbortController()
    loadFindings(city, ctrl.signal)
      .then(async (f) => {
        setFindings(f)
        document.title = `Varshik report: ${f.cityName}`
        const analyses = await Promise.all(f.surveys.map((s) => loadAnalysis(s.sequence, 'lth', ctrl.signal).catch(() => null)))
        setTracks(
          analyses
            .filter((a): a is Analysis => !!a)
            .flatMap((a) => {
              const by = new Map<string, [number, number][]>()
              for (const fr of [...a.frames].sort((x, y) => x.index - y.index)) by.set(fr.segment, [...(by.get(fr.segment) ?? []), [fr.lng, fr.lat]])
              return [...by.values()]
            }),
        )
      })
      .catch((e) => !ctrl.signal.aborted && setError(String(e)))
    return () => ctrl.abort()
  }, [city])

  // ?print=1 (Export PDF from the dashboard): open the print dialog once the frames have loaded.
  useEffect(() => {
    if (!autoPrint || !findings || !tracks.length) return
    const imgs = [...document.querySelectorAll<HTMLImageElement>('.report img')]
    Promise.all(imgs.map((i) => (i.complete ? Promise.resolve() : new Promise((r) => i.addEventListener('load', r, { once: true })))))
      .then(() => new Promise((r) => setTimeout(r, 300)))
      .then(() => window.print())
  }, [autoPrint, findings, tracks])

  if (error) return <div className="report-wrap"><p className="rep-error">Report not available: {error}. Run backend/scripts/build_findings.py --city {city}.</p></div>
  if (!findings) return <div className="report-wrap"><p className="rep-error">Loading report…</p></div>

  const counts = { urgent: 0, high: 0, watch: 0 }
  for (const s of findings.spots) counts[s.priority]++
  const needed = findings.spots.reduce((t, s) => t + (s.sizing.requiredLs ?? 0), 0)

  return (
    <MotionConfig transition={{ duration: 0 }}>
      <div className="report-wrap">
        <nav className="rep-toolbar">
          <a href="/map">
            <ArrowLeft size={14} /> Back to the map
          </a>
          <button onClick={() => window.print()}>
            <FilePdf size={16} weight="bold" /> Save as PDF
          </button>
        </nav>

        <article className="report">
          <header className="rep-cover">
            <div className="rep-brand">
              <span className="rep-logo">
                <Drop size={14} weight="fill" />
              </span>
              Varshik
            </div>
            <span className="rep-kicker">Pre-monsoon waterlogging report</span>
            <h1>{findings.cityName}</h1>
            <p className="rep-lede">
              Where roads will hold water in the monsoon, why, and how much drainage each spot needs. Found from ordinary dashcam drives, the phone's own
              sensors, satellite elevation and the city's storm statistics.
            </p>
            <p className="rep-meta">
              Generated {fmtDate(findings.generatedAt)}. Surveys: {findings.surveys.map((s) => `${s.segments.join(' / ')} (${s.date})`).join('; ')}.
            </p>
          </header>

          <section className="rep-summary">
            <div className="rep-stat">
              <b>{findings.kmFilmed}</b>
              <span>km of road checked</span>
            </div>
            <div className="rep-stat">
              <b>{findings.stretches}</b>
              <span>60 m stretches analysed</span>
            </div>
            <div className="rep-stat">
              <b>{findings.spots.length}</b>
              <span>
                spots to fix ({counts.urgent} urgent, {counts.high} high, {counts.watch} watch)
              </span>
            </div>
            <div className="rep-stat">
              <b>{needed.toLocaleString('en-IN')}</b>
              <span>L/s of drainage needed at these spots</span>
            </div>
          </section>

          <section className="rep-overview">
            <OverviewMap tracks={tracks} spots={findings.spots} />
            <table className="rep-table">
              <thead>
                <tr>
                  <th>Spot</th>
                  <th>Place</th>
                  <th>Cause</th>
                  <th>2-yr water</th>
                  <th>Drainage needed</th>
                  <th>Priority</th>
                </tr>
              </thead>
              <tbody>
                {findings.spots.map((s) => (
                  <tr key={s.id}>
                    <td className="mono">{s.id}</td>
                    <td>{s.name}</td>
                    <td>{CAUSE_SHORT[s.cause]}</td>
                    <td className="mono">{s.depthCm['2'].toFixed(0)} cm</td>
                    <td className="mono">
                      {s.sizing.requiredLs ?? 'n/a'} L/s
                    </td>
                    <td>
                      <span className="rep-chip" style={{ ['--c' as string]: PRIORITY[s.priority].color }}>
                        {PRIORITY[s.priority].label}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="rep-small">
              Priority: urgent = 20 cm or more in a 2-year storm, or 15 cm or more at an underpass or channel crossing; high = 10 to 20 cm; watch = 5 to 10
              cm. 30 cm makes a road unsafe for two-wheelers.
            </p>
          </section>

          {findings.spots.map((s, i) => (
            <SpotSection key={s.id} spot={s} index={i} city={findings.city} />
          ))}

          <BriefSection city={findings.city} />

          <section className="rep-method break">
            <h2>How these numbers are made</h2>
            <ol>
              <li>
                <b>See the road.</b> Every dashcam frame is segmented (SegFormer-B2), turned into a depth map (Depth Anything V2) and fitted with the road's
                curved surface; dips below it and potholes (YOLOv8) are measured in centimetres.
              </li>
              <li>
                <b>Feel the road.</b> The phone's tilt sensor, corrected for braking with GPS speed, gives the road's height profile. Sags and underpasses
                that 30 m satellite elevation cannot see show up here.
              </li>
              <li>
                <b>Know the land.</b> FABDEM bare-earth elevation gives hollows and how much land drains to each point; OpenStreetMap gives the drains.
              </li>
              <li>
                <b>Predict the water.</b> A water balance per 60 m stretch: rain beyond what the drains take, 85% of it running off, for a 15-minute
                burst, collected in the hollow or sag. Storms: {findings.stormSource}.
              </li>
              <li>
                <b>Size the fix.</b> The same model run backwards gives the drainage (litres per second) that keeps the 2-year storm below 5 cm.
              </li>
            </ol>
            <h3>Limits</h3>
            <p>
              A screening tool, not a drainage design. Today's real drain capacity is not published for either city, so it is not shown; drains are
              credited only with the documented design standard ({findings.drainStandard ?? 'city standard'}) where one serves the road. Blockage and
              pipe hydraulics are not modelled; a single sensor sag is a lead to check on site. Confirm each spot with a site visit before design.
            </p>
            <h3>Data and licences</h3>
            <p>
              Drains: {findings.drainsSource ?? 'OpenStreetMap'}. Street imagery: {findings.surveys.map((s) => s.attribution).join(' ')} Elevation: FABDEM (University of
              Bristol, CC BY-NC-SA 4.0) and Copernicus DEM (AWS Registry of Open Data). Drains and roads: OpenStreetMap contributors (ODbL). Rain
              history: Open-Meteo (CC BY 4.0).
            </p>
          </section>
        </article>
      </div>
    </MotionConfig>
  )
}
