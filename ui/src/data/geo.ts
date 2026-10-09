import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import routeCoords from './route.json'
import { HOTSPOTS, RISK_COLORS, riskColor } from './hotspots'

// Real road geometry (OSRM, OpenStreetMap): New Delhi station -> Minto Bridge -> ITO -> Pragati Maidan.
export const ROUTE = routeCoords as [number, number][]
export const ROUTE_NAME = { from: 'New Delhi station', to: 'Pragati Maidan' }

const R = 6371000
export function distance(a: [number, number], b: [number, number]) {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b[1] - a[1])
  const dLng = toRad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

const cumulative = ROUTE.reduce<number[]>((acc, p, i) => {
  acc.push(i === 0 ? 0 : acc[i - 1] + distance(ROUTE[i - 1], p))
  return acc
}, [])
export const ROUTE_LENGTH = cumulative[cumulative.length - 1]

/** Hotspots within 250 m of the route, ordered along it. */
export const ROUTE_HOTSPOTS = HOTSPOTS.map((h) => {
  let best = Infinity
  let at = 0
  ROUTE.forEach((p, i) => {
    const d = distance(p, h.lngLat)
    if (d < best) {
      best = d
      at = cumulative[i]
    }
  })
  return { hotspot: h, offset: best, at }
})
  .filter((x) => x.offset < 250)
  .sort((a, b) => a.at - b.at)

/** Risk (0-100) at each route vertex: nearest hotspot influence with distance falloff. */
const routeRisk = ROUTE.map((p) => {
  let r = 8
  for (const h of HOTSPOTS) {
    const d = distance(p, h.lngLat)
    r = Math.max(r, h.score * Math.exp(-d / 260))
  }
  return r
})

/** Stops for a MapLibre line-gradient: [progress, color, progress, color, ...]. */
export const ROUTE_GRADIENT_STOPS: (number | string)[] = (() => {
  const stops: (number | string)[] = []
  const samples = 48
  for (let s = 0; s <= samples; s++) {
    const target = (s / samples) * ROUTE_LENGTH
    const i = Math.max(0, cumulative.findIndex((c) => c >= target))
    stops.push(s / samples, riskColor(routeRisk[i]))
  }
  return stops
})()

/** Elevation profile along the route (mock): near-flat road with dips at hotspots. */
export const ELEVATION_PROFILE = (() => {
  const n = 120
  const points: { d: number; e: number }[] = []
  for (let s = 0; s <= n; s++) {
    const d = (s / n) * ROUTE_LENGTH
    let e = 211.5 + Math.sin(d / 420) * 0.35 + Math.sin(d / 137) * 0.15
    for (const { hotspot, at } of ROUTE_HOTSPOTS) {
      e += hotspot.relative * Math.exp(-(((d - at) / 180) ** 2))
    }
    points.push({ d, e })
  }
  return points
})()

// Deterministic PRNG so the mock heatmap is identical on every load.
function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function gaussian(rand: () => number) {
  return Math.sqrt(-2 * Math.log(rand() || 1e-9)) * Math.cos(2 * Math.PI * rand())
}

export const HEAT_POINTS: FeatureCollection<Point, { w: number }> = (() => {
  const rand = mulberry32(42)
  const features: Feature<Point, { w: number }>[] = []
  const degLat = 1 / 111000
  for (const h of HOTSPOTS) {
    const count = Math.round(h.score * 0.9)
    const spread = 160 + (100 - h.score) * 4
    for (let i = 0; i < count; i++) {
      const dx = gaussian(rand) * spread
      const dy = gaussian(rand) * spread
      features.push({
        type: 'Feature',
        properties: { w: (h.score / 100) * (0.4 + rand() * 0.6) },
        geometry: { type: 'Point', coordinates: [h.lngLat[0] + (dx * degLat) / 0.877, h.lngLat[1] + dy * degLat] },
      })
    }
  }
  // City-wide background scatter: low-weight puddling spots.
  for (let i = 0; i < 420; i++) {
    features.push({
      type: 'Feature',
      properties: { w: 0.08 + rand() * 0.25 },
      geometry: { type: 'Point', coordinates: [77.08 + rand() * 0.27, 28.49 + rand() * 0.25] },
    })
  }
  // Puddle points along the route.
  ROUTE.forEach((p, i) => {
    if (i % 3) return
    features.push({ type: 'Feature', properties: { w: 0.12 + rand() * 0.2 }, geometry: { type: 'Point', coordinates: p } })
  })
  return { type: 'FeatureCollection', features }
})()

export const ROUTE_FEATURE: Feature<LineString> = {
  type: 'Feature',
  properties: {},
  geometry: { type: 'LineString', coordinates: ROUTE },
}

export const HEAT_COLOR_RAMP = [
  0, 'rgba(0,0,0,0)',
  0.15, 'rgba(37,99,235,0.25)',
  0.35, 'rgba(6,182,212,0.7)',
  0.58, RISK_COLORS[2],
  0.78, RISK_COLORS[3],
  0.95, RISK_COLORS[4],
] as const

export function routeBounds(): [[number, number], [number, number]] {
  const lngs = ROUTE.map((p) => p[0])
  const lats = ROUTE.map((p) => p[1])
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ]
}
