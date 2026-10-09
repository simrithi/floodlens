import { useCallback } from 'react'
import { AnimatePresence, useReducedMotion } from 'motion/react'
import { useLocation, useNavigate } from 'react-router'
import { MapStage } from './map/MapStage'
import { Landing } from './landing/Landing'
import { Dashboard } from './dashboard/Dashboard'
import { StreetView } from './streetview/StreetView'
import { AppStateProvider, useAppState } from './state'
import type { Mode } from './state'

function Shell() {
  const location = useLocation()
  const navigate = useNavigate()
  const reducedMotion = useReducedMotion() ?? false
  const { setSelectedId, streetView } = useAppState()
  const mode: Mode = location.pathname.startsWith('/map') ? 'app' : 'landing'

  const onHotspotClick = useCallback(
    (id: string) => {
      setSelectedId(id)
      if (mode === 'landing') navigate('/map')
    },
    [mode, navigate, setSelectedId],
  )

  return (
    <>
      {/* One map instance for the whole session, so the landing -> app transition is a camera move, not a page load. */}
      <MapStage mode={mode} reducedMotion={reducedMotion} onHotspotClick={onHotspotClick} />
      <AnimatePresence>
        {mode === 'landing' ? (
          <Landing key="landing" onEnter={() => navigate('/map')} />
        ) : (
          <Dashboard key="app" onHome={() => navigate('/')} />
        )}
      </AnimatePresence>
      <AnimatePresence>{mode === 'app' && streetView && <StreetView key="street-view" />}</AnimatePresence>
    </>
  )
}

export default function App() {
  return (
    <AppStateProvider>
      <Shell />
    </AppStateProvider>
  )
}
