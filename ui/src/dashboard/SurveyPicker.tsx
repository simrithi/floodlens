import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { CaretDown, Check, MapPin } from '@phosphor-icons/react'
import { SURVEYS } from '../data/surveys'
import { useAppState } from '../state'

/** Top-bar switch between dashcam surveys (city + drive). The map flies to the chosen one. */
export function SurveyPicker() {
  const { survey, setSurvey } = useAppState()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

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
    <div className="survey-picker" ref={ref}>
      <button className={'survey-btn' + (open ? ' is-open' : '')} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="listbox">
        <MapPin size={14} weight="fill" />
        <span className="survey-place">{survey.place}</span>
        <span className="survey-note muted">{survey.note}</span>
        <CaretDown size={12} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.ul
            className="survey-pop glass"
            role="listbox"
            aria-label="Survey"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            {SURVEYS.map((s) => (
              <li key={s.id}>
                <button
                  role="option"
                  aria-selected={s.id === survey.id}
                  className={'survey-row' + (s.id === survey.id ? ' is-active' : '')}
                  onClick={() => {
                    setSurvey(s.id)
                    setOpen(false)
                  }}
                >
                  <span className="survey-row-text">
                    <span className="survey-row-place">{s.place}</span>
                    <span className="survey-row-note">
                      {s.note}, KartaView {s.sequence}
                    </span>
                  </span>
                  {s.id === survey.id && <Check size={14} />}
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}
