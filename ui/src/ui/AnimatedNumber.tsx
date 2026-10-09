import { useEffect } from 'react'
import { motion, useReducedMotion, useSpring, useTransform } from 'motion/react'

export function AnimatedNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const reduced = useReducedMotion()
  const spring = useSpring(value, { stiffness: 120, damping: 22 })
  const text = useTransform(spring, (v) => v.toFixed(decimals))
  useEffect(() => {
    if (reduced) spring.jump(value)
    else spring.set(value)
  }, [value, reduced, spring])
  return <motion.span>{text}</motion.span>
}
