import { Drop } from '@phosphor-icons/react'

export function Logo({ onClick }: { onClick?: () => void }) {
  const content = (
    <>
      <span className="logo-mark">
        <Drop size={16} weight="fill" />
      </span>
      FloodLens
    </>
  )
  return onClick ? (
    <button className="logo" onClick={onClick} aria-label="FloodLens home">
      {content}
    </button>
  ) : (
    <span className="logo">{content}</span>
  )
}
