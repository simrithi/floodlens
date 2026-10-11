import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { StackSimple } from '@phosphor-icons/react'
import { LAYERS } from '../data/layers'
import { useAppState } from '../state'

/** Top-bar button that opens a popover of map layer switches. */
export function LayerPanel() {
  const { layers, setLayer } = useAppState()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const onCount = LAYERS.filter((l) => layers[l.id]).length

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('pointerdown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('pointerdown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="layers" ref={ref}>
      <button className={'btn' + (open ? ' is-open' : '')} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="true">
        <StackSimple size={16} />
        Layers
        <span className="mono layers-count">
          {onCount}/{LAYERS.length}
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="layers-pop glass"
            role="group"
            aria-label="Map layers"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            {LAYERS.map((l, i) => (
              <label key={l.id} className={'layer-row' + (l.sample && !LAYERS[i - 1]?.sample ? ' first-sample' : '')}>
                <input type="checkbox" role="switch" checked={layers[l.id]} onChange={(e) => setLayer(l.id, e.target.checked)} />
                <span className="switch" aria-hidden="true" />
                <span
                  className={'layer-swatch' + (l.id === 'reported' ? ' ring' : '')}
                  style={l.id === 'reported' ? undefined : { background: l.swatch }}
                  aria-hidden="true"
                />
                <span className="layer-text">
                  <span className="layer-label">
                    {l.label}
                    {l.sample && <span className="tag tag-sample">Sample</span>}
                  </span>
                  <span className="layer-note">{l.note}</span>
                </span>
              </label>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
