// Map layers the user can switch on and off from the Layers panel (dashboard only).

export type LayerId = 'measured' | 'water' | 'flow' | 'dips' | 'kerbs' | 'hollows' | 'drains' | 'reported' | 'route' | 'heatmap' | 'hotspots' | 'buildings'

export type LayerDef = {
  id: LayerId
  label: string
  note: string
  /** CSS background for the swatch next to the label. */
  swatch: string
  sample?: boolean
  defaultOn: boolean
}

export const LAYERS: LayerDef[] = [
  { id: 'measured', label: 'Measured roads', note: 'Dashcam stretches, coloured by predicted water', swatch: 'linear-gradient(90deg,#2563eb,#facc15,#ef4444)', defaultOn: true },
  { id: 'water', label: 'Water depth columns', note: 'Predicted standing water on measured roads at the current rain (height exaggerated)', swatch: '#4c9aff', defaultOn: true },
  { id: 'flow', label: 'Water flow paths', note: 'Where rain runs off the land, downhill, from bare-earth elevation (FABDEM 30 m). Paths draining 4 ha or more; wider = more land', swatch: '#9cc6ff', defaultOn: true },
  { id: 'dips', label: 'Road dips', note: 'Found in dashcam frames', swatch: '#4c9aff', defaultOn: true },
  { id: 'kerbs', label: 'Kerb lines', note: 'Road edges joined across consecutive dashcam frames', swatch: '#facc15', defaultOn: true },
  { id: 'hollows', label: 'Terrain hollows', note: 'Computed from satellite elevation (FABDEM, 30 m). Only hollows over 1 m deep; smaller ones are within the data error', swatch: 'rgba(76,154,255,0.55)', defaultOn: false },
  { id: 'drains', label: 'Storm drains', note: 'Bengaluru: official BBMP drain map (KSRSAC 2022), wider = primary rajakaluve. Delhi: OpenStreetMap (no official map is public)', swatch: '#5eead4', defaultOn: true },
  { id: 'reported', label: 'Reported hotspots', note: 'Public PWD, Traffic Police and news reports (Delhi, Bengaluru)', swatch: 'transparent', defaultOn: true },
  { id: 'route', label: 'Survey corridor', note: 'Central Delhi corridor used for the demo survey', swatch: '#7ab4ff', defaultOn: true },
  { id: 'heatmap', label: 'Risk heatmap', note: 'Sample data', swatch: 'linear-gradient(90deg,#06b6d4,#facc15,#ef4444)', sample: true, defaultOn: true },
  { id: 'hotspots', label: 'Example hotspots', note: 'Sample data', swatch: '#ef4444', sample: true, defaultOn: true },
  { id: 'buildings', label: '3D buildings', note: 'OpenStreetMap heights', swatch: '#4a4c53', defaultOn: true },
]

export type LayerState = Record<LayerId, boolean>

const STORAGE_KEY = 'floodlens.layers.v1'

export function initialLayers(): LayerState {
  const defaults = Object.fromEntries(LAYERS.map((l) => [l.id, l.defaultOn])) as LayerState
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') as Partial<LayerState> | null
    return saved ? { ...defaults, ...saved } : defaults
  } catch {
    return defaults
  }
}

export function saveLayers(state: LayerState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Storage unavailable (private mode): the choice simply is not remembered.
  }
}
