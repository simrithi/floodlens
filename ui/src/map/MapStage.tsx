import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import type { ExpressionSpecification, GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import type { Feature, FeatureCollection, Polygon } from 'geojson'
import { animate } from 'motion'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { HOTSPOTS, RISK_COLORS, riskColor, waterLevel } from '../data/hotspots'
import { dipPoints, scanTrack } from '../data/analysis'
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

  // Roads actually measured by the dashcam pipeline: dark casing + risk colour, drawn on the ground.
  const empty = { type: 'FeatureCollection' as const, features: [] }
  map.addSource('scan', { type: 'geojson', data: empty })
  map.addSource('dips', { type: 'geojson', data: empty })
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
  const { rain, selectedId, analysis, streetView } = useAppState()

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
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true },
      fadeDuration: 0,
    })
    mapRef.current = map
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
      // Frame the route inside the space left between the panels. cameraForBounds would
      // also count the landing padding still applied to the map, so compute zoom directly.
      const pad = appPadding()
      const [[w, s], [e, n]] = routeBounds()
      const lat = (s + n) / 2
      const spanM = Math.max((e - w) * 111320 * Math.cos((lat * Math.PI) / 180), (n - s) * 111320) * 1.6
      const freePx = Math.min(window.innerWidth - pad.left - pad.right, window.innerHeight - pad.top - pad.bottom)
      const zoom = Math.log2((156543.03 * Math.cos((lat * Math.PI) / 180) * freePx) / spanM)
      map.flyTo({
        center: [(w + e) / 2, lat],
        zoom,
        bearing: -18,
        pitch: 54,
        padding: pad,
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
  }, [analysis, loaded])

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
