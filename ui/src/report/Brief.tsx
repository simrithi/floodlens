import { useEffect, useState } from 'react'
import { Sparkle } from '@phosphor-icons/react'
import { API, cachedBrief, generateBrief } from '../data/aws'
import type { Brief } from '../data/aws'

const LANGS = [
  { id: 'en', label: 'English' },
  { id: 'hi', label: 'हिन्दी' },
] as const

/** One-page officer brief written by Bedrock from the findings; the Lambda rejects any brief whose numbers are not in the data. */
export function BriefSection({ city }: { city: string }) {
  const [lang, setLang] = useState<(typeof LANGS)[number]['id']>('en')
  const [brief, setBrief] = useState<Brief | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const ac = new AbortController()
    setBrief(null)
    setError('')
    cachedBrief(city, lang, ac.signal)
      .then(setBrief)
      .catch(() => {})
    return () => ac.abort()
  }, [city, lang])

  if (!API.brief && !brief) return null

  const generate = async () => {
    setBusy(true)
    setError('')
    try {
      setBrief(await generateBrief(city, lang))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rep-brief">
      <h2>Brief for the drainage engineer</h2>
      <div className="brief-tabs no-print" role="tablist">
        {LANGS.map((l) => (
          <button key={l.id} role="tab" aria-selected={lang === l.id} className={'preset' + (lang === l.id ? ' is-active' : '')} onClick={() => setLang(l.id)}>
            {l.label}
          </button>
        ))}
      </div>
      {brief ? (
        <>
          <div className="brief-text">{brief.text}</div>
          <p className="rep-small">Written by AI from the findings in this report; every number checked against them. {brief.model}, {new Date(brief.generatedAt).toLocaleDateString('en-IN')}.</p>
        </>
      ) : (
        <p className="rep-small no-print">No brief generated yet in this language.</p>
      )}
      {API.brief && (
        <button className="btn no-print" onClick={generate} disabled={busy}>
          <Sparkle size={14} weight="fill" /> {busy ? 'Writing…' : brief ? 'Regenerate' : 'Generate brief'}
        </button>
      )}
      {error && <p className="rep-error no-print">{error}</p>}
    </section>
  )
}
