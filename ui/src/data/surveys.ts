// Dashcam surveys the app can show. Each is one KartaView sequence analysed by backend/run_local.py
// (data/outputs/<sequence>-<size>/), plus the city-wide layers exported for its city.

import type { Run } from './analysis'

export type SurveyId = 'delhi' | 'blr-orr' | 'blr-bellandur'

export type Survey = {
  id: SurveyId
  city: 'delhi' | 'bengaluru'
  /** Short name for the top bar. */
  place: string
  /** One line under it. */
  note: string
  sequence: number
  runs: Run[]
  /** City-wide layers in data/outputs (backend/scripts/export_map_layers.py --city). */
  drains: string
  hollows: string
  /** Reported-hotspot check and the sample heatmap only exist for Delhi. */
  validation: boolean
  /** Reported spots for other cities (data/outputs), map context only. */
  reported?: string
}

export const SURVEYS: Survey[] = [
  {
    id: 'delhi',
    city: 'delhi',
    place: 'Central Delhi',
    note: 'ITO and Connaught Place, Dec 2021',
    sequence: 4020141,
    runs: ['lth', 'full'],
    drains: 'drains.geojson',
    hollows: 'hollows',
    validation: true,
  },
  {
    id: 'blr-orr',
    city: 'bengaluru',
    place: 'Bengaluru ORR',
    note: 'Marathahalli to Kadubeesanahalli, Sep 2021',
    sequence: 3827609,
    runs: ['lth'],
    drains: 'drains-bengaluru.geojson',
    hollows: 'hollows-bengaluru',
    validation: false,
    reported: 'reported-bengaluru.json',
  },
  {
    id: 'blr-bellandur',
    city: 'bengaluru',
    place: 'Bellandur',
    note: 'Side roads off the ORR, Aug 2024',
    sequence: 9316057,
    runs: ['lth'],
    drains: 'drains-bengaluru.geojson',
    hollows: 'hollows-bengaluru',
    validation: false,
    reported: 'reported-bengaluru.json',
  },
]

export const surveyById = (id: SurveyId) => SURVEYS.find((s) => s.id === id) ?? SURVEYS[0]
