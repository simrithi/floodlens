// SAMPLE DATA. Locations are real Delhi roads; every score and measurement
// below is mock until the dashcam pipeline produces real values.

export type Drainage = 'Blocked' | 'Partial' | 'Clear'

export type Hotspot = {
  id: string
  name: string
  area: string
  lngLat: [number, number]
  score: number
  /** predicted standing water (cm) at 100 mm/hr */
  waterAt100: number
  /** metres above sea level */
  elevation: number
  /** metres relative to surrounding roads (negative = lower) */
  relative: number
  /** road surface height below kerb (cm) */
  kerbDrop: number
  potholes: number
  drainage: Drainage
  /** flooded in 2021..2025 */
  history: [boolean, boolean, boolean, boolean, boolean]
  reasons: string[]
}

export const HOTSPOTS: Hotspot[] = [
  {
    id: 'WL-014', name: 'Minto Bridge underpass', area: 'Connaught Place',
    lngLat: [77.2234, 28.6337], score: 92, waterAt100: 64, elevation: 212.4, relative: -2.1,
    kerbDrop: 14, potholes: 3, drainage: 'Blocked', history: [true, true, false, true, true],
    reasons: ['Sits 2.1 m below the roads around it', '3 potholes hold runoff at the low point', 'Side drains choked in 2 of 3 dashcam passes'],
  },
  {
    id: 'WL-027', name: 'ITO crossing', area: 'ITO',
    lngLat: [77.2410, 28.6283], score: 84, waterAt100: 41, elevation: 207.9, relative: -1.3,
    kerbDrop: 9, potholes: 5, drainage: 'Partial', history: [true, false, true, true, true],
    reasons: ['Lowest point between two flyover ramps', '5 potholes on the left carriageway', 'Close to the Yamuna floodplain'],
  },
  {
    id: 'WL-031', name: 'Pragati Maidan tunnel exit', area: 'Pragati Maidan',
    lngLat: [77.2440, 28.6180], score: 76, waterAt100: 33, elevation: 206.6, relative: -1.8,
    kerbDrop: 6, potholes: 1, drainage: 'Partial', history: [false, true, true, false, true],
    reasons: ['Tunnel sag collects water from both ramps', 'Pump capacity exceeded above 60 mm/hr'],
  },
  {
    id: 'WL-008', name: 'Zakhira underpass', area: 'Zakhira',
    lngLat: [77.1505, 28.6605], score: 71, waterAt100: 38, elevation: 214.2, relative: -1.6,
    kerbDrop: 11, potholes: 4, drainage: 'Blocked', history: [true, true, true, false, false],
    reasons: ['Railway underpass with no gravity outfall', '4 potholes near the entry'],
  },
  {
    id: 'WL-019', name: 'Pul Prahladpur underpass', area: 'Badarpur',
    lngLat: [77.2905, 28.4990], score: 66, waterAt100: 29, elevation: 209.8, relative: -1.4,
    kerbDrop: 8, potholes: 2, drainage: 'Partial', history: [true, true, false, true, false],
    reasons: ['Underpass sag curve', 'Runoff from the Aravalli slope to the south'],
  },
  {
    id: 'WL-036', name: 'Moolchand underpass', area: 'Lajpat Nagar',
    lngLat: [77.2340, 28.5650], score: 58, waterAt100: 22, elevation: 213.1, relative: -0.9,
    kerbDrop: 7, potholes: 2, drainage: 'Partial', history: [false, true, false, true, false],
    reasons: ['Shallow underpass', 'Road 7 cm below the kerb line'],
  },
  {
    id: 'WL-042', name: 'Azadpur Mandi road', area: 'Azadpur',
    lngLat: [77.1775, 28.7075], score: 52, waterAt100: 18, elevation: 215.7, relative: -0.6,
    kerbDrop: 5, potholes: 6, drainage: 'Blocked', history: [false, false, true, true, false],
    reasons: ['6 potholes in 200 m', 'Market waste in drains'],
  },
  {
    id: 'WL-045', name: 'Kashmere Gate ISBT', area: 'Kashmere Gate',
    lngLat: [77.2280, 28.6675], score: 44, waterAt100: 14, elevation: 210.3, relative: -0.5,
    kerbDrop: 4, potholes: 2, drainage: 'Clear', history: [false, false, true, false, false],
    reasons: ['Near the Yamuna, high groundwater', 'Mostly drains within an hour'],
  },
  {
    id: 'WL-051', name: 'Ashram Chowk', area: 'Ashram',
    lngLat: [77.2580, 28.5715], score: 41, waterAt100: 12, elevation: 211.0, relative: -0.4,
    kerbDrop: 5, potholes: 1, drainage: 'Clear', history: [false, true, false, false, false],
    reasons: ['Uneven camber on the service lane'],
  },
  {
    id: 'WL-058', name: 'Dhaula Kuan', area: 'Dhaula Kuan',
    lngLat: [77.1615, 28.5918], score: 33, waterAt100: 8, elevation: 222.5, relative: -0.3,
    kerbDrop: 3, potholes: 1, drainage: 'Clear', history: [false, false, false, true, false],
    reasons: ['Higher ground on the ridge, drains fast'],
  },
]

export const RISK_COLORS = ['#2563eb', '#06b6d4', '#facc15', '#f97316', '#ef4444'] as const

export function riskStep(score: number) {
  return Math.min(4, Math.max(0, Math.floor(score / 20)))
}

export function riskColor(score: number) {
  return RISK_COLORS[riskStep(score)]
}

export function riskLabel(score: number) {
  return ['Drains well', 'Minor puddling', 'Moderate', 'High', 'Will waterlog'][riskStep(score)]
}

/** Predicted standing water (cm) for a rainfall rate (mm/hr). Mock model. */
export function waterLevel(h: Hotspot, rain: number) {
  const drainage = { Blocked: 0, Partial: 8, Clear: 18 }[h.drainage]
  const effective = Math.max(0, rain - drainage)
  return Math.round(h.waterAt100 * Math.pow(effective / 100, 1.15))
}

export const RAIN_PRESETS = [
  { label: 'Drizzle', value: 8 },
  { label: 'Moderate', value: 35 },
  { label: 'Heavy', value: 75 },
  { label: 'Cloudburst', value: 130 },
] as const

export const HISTORY_YEARS = [2021, 2022, 2023, 2024, 2025]
