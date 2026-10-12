/** The Varshik mark: a raindrop with a road running into it. Varshik means rain. */
export function LogoMark({ size = 20 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <path d="M16 4.2C16 4.2 7.6 13.4 7.6 19.2a8.4 8.4 0 0 0 16.8 0C24.4 13.4 16 4.2 16 4.2Z" fill="currentColor" />
      <path d="M15.2 13.4h1.6l3.1 12.4h-7.8z" fill="var(--primary)" />
      <path d="M16 15.6v2.2M16 20v3.4" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    </svg>
  )
}

export function Logo({ onClick }: { onClick?: () => void }) {
  const content = (
    <>
      <span className="logo-mark">
        <LogoMark />
      </span>
      Varshik
    </>
  )
  return onClick ? (
    <button className="logo" onClick={onClick} aria-label="Varshik home">
      {content}
    </button>
  ) : (
    <span className="logo">{content}</span>
  )
}
