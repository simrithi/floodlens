import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { ExpressionSpecification, GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import type { Feature, FeatureCollection, Polygon } from 'geojson'
import { animate } from 'motion'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { HOTSPOTS, RISK_COLORS, riskColor, waterLevel } from '../data/hotspots'
import { ANALYSIS_BASE, depthAt, dipPoints, fileUrl, scanTrack } from '../data/analysis'
import type { Analysis } from '../data/analysis'
import { spotPoints } from '../data/validation'
import type { LayerId } from '../data/layers'
import { HEAT_COLOR_RAMP, HEAT_POINTS, ROUTE_FEATURE, ROUTE_GRADIENT_STOPS, routeBounds } from '../data/geo'
import { useAppState } from '../state'
import type { Mode } from '../state'
import './map.css'

maplibregl.setWorkerUrl(workerUrl)

const STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const LANDING_CAMERA = { center: [77.2318, 28.6302] as [number, number], zoom: 14.15, pitch: 66, bearing: -24 }
const CALLOUTS = new Set(['WL-014', 'WL-027'])
const DASH_SEQUENCE = [
  [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0],
  [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
]

// Map layer ids behind each toggle in the Layers panel.
const LAYER_MAP: Record<LayerId, string[]> = {
  measured: ['scan-casing', 'scan-line', 'scan-selected'],
  dips: ['dips'],
  hollows: ['hollows'],
  drains: ['drains', 'drains-covered'],
  reported: ['reference'],
  route: ['route-glow', 'route-line', 'route-flow'],
  heatmap: ['heat', 'pools'],
  water: ['cell-pools'],
  kerbs: ['kerb-lines'],
  flow: ['flow-base', 'flow-dash'],
  hotspots: [],
  buildings: ['buildings-3d'],
}
const LANDING_LAYERS = new Set<LayerId>(['heatmap', 'hotspots', 'buildings', 'route'])

const isMobile = () => window.innerWidth < 768

type Pad = { top: number; bottom: number; left: number; right: number }

function landingPadding(): Pad {
  return isMobile()
    ? { top: window.innerHeight * 0.45, bottom: 0, left: 0, right: 0 }
    : { top: 0, bottom: 0, left: window.innerWidth * 0.42, right: 0 }
}

function appPadding(): Pad {
  return isMobile()
    ? { top: 72, bottom: window.innerHeight * 0.5, left: 16, right: 16 }
    : { top: 96, bottom: 120, left: 384, right: 408 }
}

type Bounds = [[number, number], [number, number]]

/** Bounding box of the analysed frames. */
function trackBounds(a: Analysis): Bounds {
  const lngs = a.frames.map((f) => f.lng)
  const lats = a.frames.map((f) => f.lat)
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ]
}

/** Camera that fits bounds into the space left between the dashboard panels. cameraForBounds would
 *  also count the landing padding still applied to the map, so compute zoom directly. */
function appCamera([[w, s], [e, n]]: Bounds, minSpanM = 0) {
  const pad = appPadding()
  const lat = (s + n) / 2
  const spanM = Math.max((e - w) * 111320 * Math.cos((lat * Math.PI) / 180), (n - s) * 111320, minSpanM) * 1.6
  const freePx = Math.min(window.innerWidth - pad.left - pad.right, window.innerHeight - pad.top - pad.bottom)
  const zoom = Math.log2((156543.03 * Math.cos((lat * Math.PI) / 180) * freePx) / spanM)
  return { center: [(w + e) / 2, lat] as [number, number], zoom, padding: pad }
}

function circle(center: [number, number], radiusM: number, steps = 40): number[][] {
  const out: number[][] = []
  const dLat = radiusM / 111000
  const dLng = dLat / Math.cos((center[1] * Math.PI) / 180)
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * Math.PI * 2
    out.push([center[0] + Math.cos(a) * dLng, center[1] + Math.sin(a) * dLat])
  }
  return out
}

/** Real predicted water on measured stretches: one column per cell, height from its depth curve. */
function cellPoolData(analysis: Analysis | null, rain: number): FeatureCollection<Polygon> {
  if (!analysis) return { type: 'FeatureCollection', features: [] }
  return {
    type: 'FeatureCollection',
    features: analysis.cells.map<Feature<Polygon>>((c) => {
      const depthCm = depthAt(c.water, rain)
      return {
        type: 'Feature',
        properties: { id: c.id, depthCm, h: depthCm * 0.55 },
        geometry: { type: 'Polygon', coordinates: [circle([c.lng, c.lat], 16 + Math.min(14, Math.sqrt(c.water.poolM2) / 3))] },
      }
    }),
  }
}

function poolData(rain: number): FeatureCollection<Polygon> {
  return {
    type: 'FeatureCollection',
    features: HOTSPOTS.map<Feature<Polygon>>((h) => ({
      type: 'Feature',
      properties: { h: waterLevel(h, rain) * 0.55 },
      geometry: { type: 'Polygon', coordinates: [circle(h.lngLat, 45 + h.score * 0.9)] },
    })),
  }
}

/** line-gradient that reveals the route up to `p` (0..1). */
function routeGradient(p: number): ExpressionSpecification {
  const clear = 'rgba(0,0,0,0)'
  // Near the end the cut-off stop would not be strictly after `p`, so show the full route.
  if (p >= 0.995) return ['interpolate', ['linear'], ['line-progress'], ...ROUTE_GRADIENT_STOPS] as ExpressionSpecification
  if (p <= 0.001) return ['interpolate', ['linear'], ['line-progress'], 0, clear, 1, clear]
  const stops: (number | string)[] = []
  let last = ROUTE_GRADIENT_STOPS[1] as string
  for (let i = 0; i < ROUTE_GRADIENT_STOPS.length; i += 2) {
    const at = ROUTE_GRADIENT_STOPS[i] as number
    if (at >= p) break
    last = ROUTE_GRADIENT_STOPS[i + 1] as string
    stops.push(at, last)
  }
  stops.push(p, last, Math.min(p + 0.002, 0.999), clear, 1, clear)
  return ['interpolate', ['linear'], ['line-progress'], ...stops] as ExpressionSpecification
}

function setupLayers(map: MlMap) {
  const firstSymbol = map.getStyle().layers.find((l) => l.type === 'symbol')?.id

  for (const id of ['building', 'building-top']) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'none')
  }

  // Slightly lift the road network so the city reads as grey on black.
  for (const layer of map.getStyle().layers) {
    if (layer.type === 'line' && /^road_(pri|sec|trunk|mot)_fill/.test(layer.id)) {
      map.setPaintProperty(layer.id, 'line-color', '#3b3e45')
    }
  }

  map.addSource('heat', { type: 'geojson', data: HEAT_POINTS })
  map.addSource('route', { type: 'geojson', data: ROUTE_FEATURE, lineMetrics: true })
  map.addSource('pools', { type: 'geojson', data: poolData(75) })
  map.addSource('cell-pools', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })

  map.addLayer(
    {
      id: 'heat',
      type: 'heatmap',
      source: 'heat',
      paint: {
        'heatmap-weight': ['get', 'w'],
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 10, 0.7, 15, 1.6],
        'heatmap-radius': ['interpolate', ['exponential', 1.5], ['zoom'], 10, 10, 13, 26, 16, 75],
        'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], ...HEAT_COLOR_RAMP] as ExpressionSpecification,
        'heatmap-opacity': 0.72,
      },
    },
    firstSymbol,
  )

  map.addLayer(
    {
      id: 'route-glow',
      type: 'line',
      source: 'route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-width': 16, 'line-blur': 10, 'line-opacity': 0.55, 'line-gradient': routeGradient(0) },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'route-line',
      type: 'line',
      source: 'route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-width': 4.5, 'line-gradient': routeGradient(0) },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'route-flow',
      type: 'line',
      source: 'route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-width': 2, 'line-color': '#f7f8f8', 'line-opacity': 0, 'line-dasharray': [0, 4, 3], 'line-opacity-transition': { duration: 600 } },
    },
    firstSymbol,
  )

  // Drainage network from OpenStreetMap (backend/core/drainage.py): drains, canals, rivers.
  // Solid = open channel, dashed = covered (tunnel). Drawn on the ground under the measured track.
  map.addSource('drains', { type: 'geojson', data: `${ANALYSIS_BASE}/drains.geojson` })
  const drainColor = '#5eead4'
  map.addLayer(
    {
      id: 'drains',
      type: 'line',
      source: 'drains',
      filter: ['!', ['get', 'tunnel']],
      layout: { 'line-cap': 'round', visibility: 'none' },
      // Official maps carry a tier (primary rajakaluve > secondary > tertiary roadside drain); OSM carries river/canal/drain.
      paint: {
        'line-color': drainColor,
        'line-opacity': ['match', ['get', 'class'], 'tertiary', 0.55, 0.95],
        'line-width': [
          'interpolate', ['linear'], ['zoom'],
          11, ['match', ['get', 'class'], ['river', 'canal', 'primary'], 2.4, 'secondary', 1.5, 'tertiary', 0.7, 1.4],
          16, ['match', ['get', 'class'], ['river', 'canal', 'primary'], 7, 'secondary', 4, 'tertiary', 2, 4],
        ],
      },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'drains-covered',
      type: 'line',
      source: 'drains',
      filter: ['get', 'tunnel'],
      layout: { visibility: 'none' },
      paint: {
        'line-color': drainColor,
        'line-opacity': 0.8,
        'line-dasharray': [1.2, 1.2],
        'line-width': ['interpolate', ['linear'], ['zoom'], 11, 1.2, 16, 3.5],
      },
    },
    firstSymbol,
  )

  // Surface-water flow paths from bare-earth elevation (backend/scripts/export_flow.py), drawn downhill
  // with moving dashes so you can see where rain runs to. Wider = more land draining through.
  const empty = { type: 'FeatureCollection' as const, features: [] }
  map.addSource('flow', { type: 'geojson', data: empty })
  const flowWidth: ExpressionSpecification = ['interpolate', ['linear'], ['ln', ['max', 1, ['get', 'upstreamHa']]], 1.4, 1, 10, 4.5]
  map.addLayer(
    {
      id: 'flow-base',
      type: 'line',
      source: 'flow',
      layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' },
      paint: { 'line-color': '#4c9aff', 'line-opacity': 0.28, 'line-width': flowWidth },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'flow-dash',
      type: 'line',
      source: 'flow',
      layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' },
      paint: { 'line-color': '#9cc6ff', 'line-opacity': 0.9, 'line-width': flowWidth, 'line-dasharray': [0, 4, 3] },
    },
    firstSymbol,
  )

  // Roads actually measured by the dashcam pipeline: dark casing + risk colour, drawn on the ground.
  map.addSource('scan', { type: 'geojson', data: empty })
  map.addSource('dips', { type: 'geojson', data: empty })
  map.addSource('kerb-lines', { type: 'geojson', data: empty })
  const riskStepColor: ExpressionSpecification = [
    'step', ['get', 'risk'], RISK_COLORS[0], 20, RISK_COLORS[1], 40, RISK_COLORS[2], 60, RISK_COLORS[3], 80, RISK_COLORS[4],
  ]
  map.addLayer(
    {
      id: 'scan-casing',
      type: 'line',
      source: 'scan',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#f7f8f8', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 4, 16, 12], 'line-opacity': 0.9 },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'scan-line',
      type: 'line',
      source: 'scan',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': riskStepColor, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 2.5, 16, 8] },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'scan-selected',
      type: 'line',
      source: 'scan',
      filter: ['==', ['get', 'id'], ''],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': riskStepColor, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 8, 16, 22], 'line-blur': 6, 'line-opacity': 0.8 },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'kerb-lines',
      type: 'line',
      source: 'kerb-lines',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#facc15', 'line-width': ['interpolate', ['linear'], ['zoom'], 14, 1, 18, 3.5], 'line-opacity': 0.9 },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'dips',
      type: 'circle',
      source: 'dips',
      minzoom: 13.5,
      paint: {
        'circle-color': '#4c9aff',
        'circle-radius': ['interpolate', ['linear'], ['get', 'areaM2'], 0.4, 3, 6, 8],
        'circle-stroke-color': '#0f1011',
        'circle-stroke-width': 1.5,
        'circle-opacity': 0.9,
      },
    },
    firstSymbol,
  )

  map.addLayer(
    {
      id: 'buildings-3d',
      type: 'fill-extrusion',
      source: 'carto',
      'source-layer': 'building',
      minzoom: 12.5,
      filter: ['!=', ['get', 'hide_3d'], true],
      paint: {
        'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 8], 0, '#1b1c20', 25, '#2e3036', 60, '#4a4c53', 140, '#7c7e86'],
        'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 12.5, 0, 13.5, ['coalesce', ['get', 'render_height'], 8]],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
        'fill-extrusion-opacity': 0.92,
        'fill-extrusion-vertical-gradient': true,
      },
    },
    firstSymbol,
  )

  map.addLayer(
    {
      id: 'pools',
      type: 'fill-extrusion',
      source: 'pools',
      paint: {
        'fill-extrusion-color': '#4c9aff',
        'fill-extrusion-height': ['get', 'h'],
        'fill-extrusion-base': 0,
        'fill-extrusion-opacity': 0.5,
      },
    },
    firstSymbol,
  )
  map.addLayer(
    {
      id: 'cell-pools',
      type: 'fill-extrusion',
      source: 'cell-pools',
      paint: {
        // Light blue for shallow water, deeper blue once it is unsafe for two-wheelers (30 cm).
        'fill-extrusion-color': ['interpolate', ['linear'], ['get', 'depthCm'], 0, '#9cc9ff', 15, '#4c9aff', 30, '#2563eb'],
        'fill-extrusion-height': ['get', 'h'],
        'fill-extrusion-base': 0,
        'fill-extrusion-opacity': 0.7,
      },
    },
    firstSymbol,
  )

  // Publicly reported waterlogging hotspots used for validation: white rings above the buildings, app mode only.
  map.addSource('reference', { type: 'geojson', data: empty })
  map.addLayer(
    {
      id: 'reference',
      type: 'circle',
      source: 'reference',
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 4, 15, 9],
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-color': '#f7f8f8',
        'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 15, 2.5],
        'circle-stroke-opacity': 0.85,
      },
    },
    firstSymbol,
  )

  map.setLight({ anchor: 'viewport', color: '#ffffff', intensity: 0.32, position: [1.2, 200, 35] })
}

type Props = {
  mode: Mode
  reducedMotion: boolean
  onHotspotClick: (id: string) => void
}

export function MapStage({ mode, reducedMotion, onHotspotClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const markersRef = useRef(new Map<string, HTMLElement>())
  const clickRef = useRef(onHotspotClick)
  const rainRef = useRef(75)
  const firstModeRef = useRef(true)
  const prevSelectedRef = useRef<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const cameraRef = useRef<maplibregl.Marker | null>(null)
  const { rain, selectedId, analysis, streetView, reported, layers, survey } = useAppState()
  const [hollowsReady, setHollowsReady] = useState(false)
  const analysisRef = useRef(analysis)
  analysisRef.current = analysis
  const surveyRef = useRef(survey)
  surveyRef.current = survey
  const flownSurveyRef = useRef<string | null>(null)

  clickRef.current = onHotspotClick

  // Create the map once; it stays mounted across landing <-> app.
  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current!,
      style: STYLE,
      center: [77.215, 28.62],
      zoom: 10.8,
      pitch: 20,
      bearing: 0,
      maxPitch: 78,
      // Linear rotation: horizontal drag always turns the same way. MapLibre's default "orbital" mode
      // reverses direction when the cursor crosses the screen centre, which feels inverted while tilting.
      aroundCenter: false,
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true },
      fadeDuration: 0,
    })
    mapRef.current = map
    // Zoom, compass and tilt controls (dashboard only, see map.css). The compass resets bearing and pitch.
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true, showCompass: true, showZoom: true }), 'top-right')
    if (import.meta.env.DEV) (window as unknown as { __map: MlMap }).__map = map

    map.on('load', () => {
      setupLayers(map)
      for (const h of HOTSPOTS) {
        const el = document.createElement('button')
        el.className = 'hs' + (CALLOUTS.has(h.id) ? ' is-callout' : '')
        el.style.setProperty('--c', riskColor(h.score))
        el.style.setProperty('--s', `${8 + h.score / 9}px`)
        el.setAttribute('aria-label', `${h.name}, risk ${h.score}`)
        el.innerHTML = `<span class="hs-ring"></span><span class="hs-core"></span><span class="hs-label"><b>${h.score}</b>${h.name}</span>`
        el.addEventListener('click', (e) => {
          e.stopPropagation()
          clickRef.current(h.id)
        })
        new maplibregl.Marker({ element: el }).setLngLat(h.lngLat).addTo(map)
        markersRef.current.set(h.id, el)
      }
      map.on('click', 'scan-line', (e) => {
        const id = e.features?.[0]?.properties?.id
        if (typeof id === 'string') clickRef.current(id)
      })
      const refPopup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'ref-popup', offset: 10 })
      map.on('mousemove', 'reference', (e) => {
        const f = e.features?.[0]
        if (!f || f.geometry.type !== 'Point') return
        const el = document.createElement('div')
        const name = document.createElement('b')
        const kind = document.createElement('span')
        name.textContent = String(f.properties?.name ?? '')
        kind.textContent = f.properties?.official ? 'Official hotspot' : 'Reported waterlogging'
        el.append(name, kind)
        refPopup.setLngLat(f.geometry.coordinates as [number, number]).setDOMContent(el).addTo(map)
      })
      map.on('mouseleave', 'reference', () => refPopup.remove())
      map.on('mouseenter', 'scan-line', () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', 'scan-line', () => (map.getCanvas().style.cursor = ''))
      setLoaded(true)
    })

    return () => {
      map.remove()
      mapRef.current = null
      markersRef.current.clear()
    }
  }, [])

  // City-wide layers of the chosen survey: drains and bare-earth hollows (backend/scripts/export_map_layers.py).
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    ;(map.getSource('drains') as GeoJSONSource).setData(`${ANALYSIS_BASE}/${survey.drains}`)
    const ctrl = new AbortController()
    fetch(`${ANALYSIS_BASE}/${survey.hollows}.json`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((meta: { coordinates: [[number, number], [number, number], [number, number], [number, number]] }) => {
        const url = `${ANALYSIS_BASE}/${survey.hollows}.png`
        const src = map.getSource('hollows') as maplibregl.ImageSource | undefined
        if (src) {
          src.updateImage({ url, coordinates: meta.coordinates })
          return
        }
        map.addSource('hollows', { type: 'image', url, coordinates: meta.coordinates })
        map.addLayer(
          { id: 'hollows', type: 'raster', source: 'hollows', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.85, 'raster-resampling': 'nearest' } },
          'drains',
        )
        setHollowsReady(true)
      })
      .catch(() => !ctrl.signal.aborted && console.warn(`Varshik: ${survey.hollows} layer not available`))
    return () => ctrl.abort()
  }, [survey, loaded])

  // Switching survey in the dashboard: fly to the new drive once its analysis has loaded.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded || mode !== 'app' || flownSurveyRef.current === null) return
    if (flownSurveyRef.current === survey.id) return
    if (!survey.validation && analysis?.sequence.id !== survey.sequence) return
    flownSurveyRef.current = survey.id
    map.flyTo({
      ...appCamera(survey.validation || !analysis ? routeBounds() : trackBounds(analysis), survey.validation ? 0 : 1200),
      bearing: -18,
      pitch: 54,
      duration: reducedMotion ? 0 : 3200,
      curve: 1.5,
      essential: true,
    })
  }, [survey, analysis, loaded, mode, reducedMotion])

  // Camera choreography per mode.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    const first = firstModeRef.current
    firstModeRef.current = false
    const container = map.getContainer()
    container.dataset.mode = mode

    const stops: (() => void)[] = []
    const duration = (ms: number) => (reducedMotion ? 0 : ms)

    if (mode === 'landing') {
      map.scrollZoom.disable()
      map.setPaintProperty('route-flow', 'line-opacity', 0)
      const routeOut = animate(1, 0, { duration: reducedMotion ? 0 : 0.5, onUpdate: (p) => {
        map.setPaintProperty('route-line', 'line-gradient', routeGradient(p))
        map.setPaintProperty('route-glow', 'line-gradient', routeGradient(p))
      } })
      stops.push(() => routeOut.stop())

      map.flyTo({
        ...LANDING_CAMERA,
        padding: landingPadding(),
        duration: duration(first ? 3600 : 2400),
        curve: 1.2,
        essential: true,
        easing: (t) => 1 - Math.pow(1 - t, 3),
      })

      // Slow orbit once the camera settles; pauses while the user drags.
      if (!reducedMotion) {
        let raf = 0
        let paused = false
        let resumeTimer = 0
        const spin = () => {
          if (!paused) map.setBearing(map.getBearing() + 0.035)
          raf = requestAnimationFrame(spin)
        }
        const pause = () => {
          paused = true
          window.clearTimeout(resumeTimer)
        }
        const resume = () => {
          window.clearTimeout(resumeTimer)
          resumeTimer = window.setTimeout(() => (paused = false), 2500)
        }
        const start = () => {
          raf = requestAnimationFrame(spin)
          map.on('mousedown', pause)
          map.on('touchstart', pause)
          map.on('mouseup', resume)
          map.on('touchend', resume)
        }
        map.once('moveend', start)
        stops.push(() => {
          map.off('moveend', start)
          cancelAnimationFrame(raf)
          window.clearTimeout(resumeTimer)
          map.off('mousedown', pause)
          map.off('touchstart', pause)
          map.off('mouseup', resume)
          map.off('touchend', resume)
        })
      }
    } else {
      map.scrollZoom.enable()
      // Delhi: frame the survey corridor. Other cities: frame the analysed drive.
      const a = analysisRef.current
      const other = !surveyRef.current.validation && a && a.sequence.id === surveyRef.current.sequence
      flownSurveyRef.current = other ? surveyRef.current.id : 'delhi'
      map.flyTo({
        ...appCamera(other ? trackBounds(a) : routeBounds(), other ? 1200 : 0),
        bearing: -18,
        pitch: 54,
        duration: duration(first ? 2200 : 2600),
        curve: 1.35,
        essential: true,
        easing: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
      })

      // Draw the route in as the camera lands, then start the flow dashes.
      const drawTimer = window.setTimeout(() => {
        const draw = animate(0, 1, {
          duration: reducedMotion ? 0 : 1.6,
          ease: [0.65, 0, 0.35, 1],
          onUpdate: (p) => {
            map.setPaintProperty('route-line', 'line-gradient', routeGradient(p))
            map.setPaintProperty('route-glow', 'line-gradient', routeGradient(p))
          },
          onComplete: () => map.setPaintProperty('route-flow', 'line-opacity', 0.7),
        })
        stops.push(() => draw.stop())
      }, duration(1500))
      stops.push(() => window.clearTimeout(drawTimer))

      if (!reducedMotion) {
        let step = 0
        const dash = window.setInterval(() => {
          step = (step + 1) % DASH_SEQUENCE.length
          map.setPaintProperty('route-flow', 'line-dasharray', DASH_SEQUENCE[step])
          map.setPaintProperty('flow-dash', 'line-dasharray', DASH_SEQUENCE[step])
        }, 55)
        stops.push(() => window.clearInterval(dash))
      }
    }

    return () => stops.forEach((s) => s())
  }, [mode, loaded, reducedMotion])

  // Rain drives heatmap intensity and the water pools.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    const from = rainRef.current
    const controls = animate(from, rain, {
      duration: reducedMotion ? 0 : 0.6,
      ease: 'easeOut',
      onUpdate: (r) => {
        rainRef.current = r
        const k = 0.28 + (r / 100) * 0.72
        map.setPaintProperty('heat', 'heatmap-intensity', ['interpolate', ['linear'], ['zoom'], 10, 0.5 * k, 15, 1.1 * k])
        ;(map.getSource('pools') as GeoJSONSource).setData(poolData(r))
        ;(map.getSource('cell-pools') as GeoJSONSource).setData(cellPoolData(analysisRef.current, r))
      },
    })
    return () => controls.stop()
  }, [rain, loaded, reducedMotion])

  // Measured roads and dips from the pipeline (swap when the run changes).
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    ;(map.getSource('scan') as GeoJSONSource).setData(analysis ? scanTrack(analysis) : { type: 'FeatureCollection', features: [] })
    ;(map.getSource('dips') as GeoJSONSource).setData(analysis ? dipPoints(analysis) : { type: 'FeatureCollection', features: [] })
    ;(map.getSource('cell-pools') as GeoJSONSource).setData(cellPoolData(analysis, rainRef.current))
    // Flow paths around the drive (backend/scripts/export_flow.py); absent file -> empty layer.
    const flowSource = map.getSource('flow') as GeoJSONSource
    if (analysis) {
      fetch(fileUrl(analysis, 'flow.geojson'))
        .then((r) => (r.ok ? r.json() : { type: 'FeatureCollection', features: [] }))
        .then((g) => flowSource.setData(g))
        .catch(() => flowSource.setData({ type: 'FeatureCollection', features: [] }))
    } else {
      flowSource.setData({ type: 'FeatureCollection', features: [] })
    }
    // Kerb lines joined across frames (backend/scripts/build_continuity.py); absent file -> empty layer.
    const kerbSource = map.getSource('kerb-lines') as GeoJSONSource
    if (analysis) {
      fetch(fileUrl(analysis, 'kerb_lines.geojson'))
        .then((r) => (r.ok ? r.json() : { type: 'FeatureCollection', features: [] }))
        .then((g) => kerbSource.setData(g))
        .catch(() => kerbSource.setData({ type: 'FeatureCollection', features: [] }))
    } else {
      kerbSource.setData({ type: 'FeatureCollection', features: [] })
    }
  }, [analysis, loaded])

  // Layer toggles (dashboard). The landing page keeps its fixed look: heatmap, hotspots, buildings.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    const on = (id: LayerId) => (mode === 'app' ? layers[id] : LANDING_LAYERS.has(id))
    for (const [id, mapIds] of Object.entries(LAYER_MAP) as [LayerId, string[]][]) {
      for (const mapId of mapIds) {
        if (map.getLayer(mapId)) map.setLayoutProperty(mapId, 'visibility', on(id) ? 'visible' : 'none')
      }
    }
    markersRef.current.forEach((el) => (el.style.visibility = on('hotspots') ? 'visible' : 'hidden'))
  }, [mode, layers, loaded, hollowsReady])

  // Reported hotspots for the current survey's city (state.reported).
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    ;(map.getSource('reference') as GeoJSONSource).setData(spotPoints(reported))
  }, [reported, loaded])

  // Street view camera: a heading cone at the frame being viewed.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    const frame = streetView && analysis?.frames.find((f) => f.index === streetView.index)
    if (!frame) {
      cameraRef.current?.remove()
      cameraRef.current = null
      return
    }
    if (!cameraRef.current) {
      const el = document.createElement('div')
      el.className = 'sv-camera'
      el.innerHTML = '<span class="sv-camera-cone"></span><span class="sv-camera-dot"></span>'
      cameraRef.current = new maplibregl.Marker({ element: el, rotationAlignment: 'map', pitchAlignment: 'map' })
        .setLngLat([frame.lng, frame.lat])
        .addTo(map)
    }
    cameraRef.current.setLngLat([frame.lng, frame.lat]).setRotation(frame.heading ?? 0)
    map.easeTo({ center: [frame.lng, frame.lat], duration: reducedMotion ? 0 : 400 })
  }, [streetView, analysis, loaded, reducedMotion])

  // Selection: highlight marker or measured stretch, and in app mode bring it into view.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !loaded) return
    markersRef.current.forEach((el, id) => el.classList.toggle('is-selected', id === selectedId))
    map.setFilter('scan-selected', ['==', ['get', 'id'], selectedId])
    const prev = prevSelectedRef.current
    prevSelectedRef.current = selectedId
    if (mode !== 'app' || prev === null || prev === selectedId) return
    const h = HOTSPOTS.find((x) => x.id === selectedId)
    const cell = analysis?.cells.find((c) => c.id === selectedId)
    const center: [number, number] | null = h ? h.lngLat : cell ? [cell.lng, cell.lat] : null
    if (!center) return
    map.flyTo({
      center,
      zoom: 15.6,
      pitch: 62,
      bearing: map.getBearing() - 25,
      padding: appPadding(),
      duration: reducedMotion ? 0 : 2000,
      curve: 1.4,
      essential: true,
    })
  }, [selectedId, loaded, mode, reducedMotion, analysis])

  return <div ref={containerRef} className={'map-stage' + (loaded ? ' is-loaded' : '')} />
}
