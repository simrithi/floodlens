import { motion } from 'motion/react'
import type { Variants } from 'motion/react'
import { ArrowRight } from '@phosphor-icons/react'
import { Logo } from '../ui/Logo'
import { RISK_COLORS } from '../data/hotspots'
import './landing.css'

const ease = [0.16, 1, 0.3, 1] as const

const stack: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09, delayChildren: 0.35 } },
  exit: { transition: { staggerChildren: 0.05 } },
}

const item: Variants = {
  hidden: { opacity: 0, y: 28, filter: 'blur(10px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { type: 'spring', stiffness: 90, damping: 20 } },
  exit: { opacity: 0, x: -56, filter: 'blur(12px)', transition: { duration: 0.55, ease } },
}

export function Landing({ onEnter }: { onEnter: () => void }) {
  return (
    <motion.div className="landing" initial="hidden" animate="show" exit="exit">
      <motion.div
        className="landing-scrim"
        aria-hidden="true"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1, transition: { duration: 1.2 } }}
        exit={{ opacity: 0, transition: { duration: 1.1, ease } }}
      />

      <motion.header className="landing-nav" variants={item}>
        <Logo />
      </motion.header>

      <motion.main className="landing-hero" variants={stack}>
        <motion.p className="landing-eyebrow" variants={item}>
          AWS Bharat Builds, Heat and Water track
        </motion.p>
        <motion.h1 className="landing-title" variants={item}>
          See where your city floods <span>before it rains.</span>
        </motion.h1>
        <motion.p className="landing-sub" variants={item}>
          FloodLens reads dashcam footage, satellite elevation and rain history to map every road that will flood.
        </motion.p>
        <motion.div variants={item}>
          <motion.button
            className="cta"
            onClick={onEnter}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
          >
            Try now
            <span className="cta-icon">
              <ArrowRight size={20} weight="bold" />
            </span>
          </motion.button>
        </motion.div>
      </motion.main>

      <motion.aside className="landing-legend" variants={item}>
        <span className="landing-legend-title">Waterlogging risk, New Delhi</span>
        <span className="landing-legend-bar" style={{ background: `linear-gradient(90deg, ${RISK_COLORS.join(', ')})` }} />
        <span className="landing-legend-labels">
          <span>Drains</span>
          <span>Floods</span>
        </span>
        <span className="landing-legend-note">Sample data</span>
      </motion.aside>
    </motion.div>
  )
}
