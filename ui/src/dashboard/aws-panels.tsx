import { useEffect, useState } from 'react'
import { Bell, Camera, ClipboardText, Sparkle } from '@phosphor-icons/react'
import { API, cachedFrameCheck, getPasscode, listActions, recordAction, runFrameCheck, setPasscode } from '../data/aws'
import type { ActionItem, FrameCheck } from '../data/aws'

const ROWS: { key: keyof FrameCheck; label: string }[] = [
  { key: 'underpass', label: 'Underpass' },
  { key: 'drainInletVisible', label: 'Drain inlet visible' },
  { key: 'inletCondition', label: 'Inlet condition' },
  { key: 'standingWaterOrStain', label: 'Standing water or stain' },
  { key: 'kerbOpeningsVisible', label: 'Kerb openings visible' },
]

/** What the vision model read in the spot's dashcam frames. Evidence to verify on site, never an input to the water model. */
export function FrameCheckResult({ check }: { check: FrameCheck }) {
  const blockage = check.blockage.filter((b) => b !== 'none')
  return (
    <div className="ai-check">
      <dl>
        {ROWS.map((r) => (
          <div key={r.key}>
            <dt>{r.label}</dt>
            <dd>{String(check[r.key])}</dd>
          </div>
        ))}
        {blockage.length > 0 && (
          <div>
            <dt>Blockage</dt>
            <dd>{blockage.join(', ')}</dd>
          </div>
        )}
      </dl>
      {check.notes && <p className="ai-notes">{check.notes}</p>}
      <p className="ai-label">
        AI read of dashcam frames: verify on site. {check.model}, {new Date(check.generatedAt).toLocaleDateString('en-IN')}.
      </p>
    </div>
  )
}

/** Cached result for a spot, if the check has been run. Nothing is called until the user asks. */
export function useCachedCheck(city: string, spotId: string) {
  const [check, setCheck] = useState<FrameCheck | null>(null)
  useEffect(() => {
    const ac = new AbortController()
    setCheck(null)
    cachedFrameCheck(city, spotId, ac.signal)
      .then(setCheck)
      .catch(() => {})
    return () => ac.abort()
  }, [city, spotId])
  return [check, setCheck] as const
}

export function FrameCheckBlock({ city, spotId }: { city: string; spotId: string }) {
  const [check, setCheck] = useCachedCheck(city, spotId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!API.frameCheck && !check) return null

  const run = async () => {
    setBusy(true)
    setError('')
    try {
      setCheck(await runFrameCheck(city, spotId))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fix-block">
      <span className="fix-step">
        <Camera size={14} weight="fill" /> What the dashcam shows
      </span>
      {check && <FrameCheckResult check={check} />}
      {API.frameCheck && (
        <button className="btn ai-btn" onClick={run} disabled={busy}>
          <Sparkle size={14} weight="fill" /> {busy ? 'Reading frames…' : check ? 'Check again' : 'Check frames with AI'}
        </button>
      )}
      {error && <p className="ai-error">{error}</p>}
    </div>
  )
}

const today = () => new Date().toISOString().slice(0, 10)

/** Officer approvals and what actually happened on the ground, stored in DynamoDB. */
export function ActionsBlock({ city, spotId, action }: { city: string; spotId: string; action?: string }) {
  const [items, setItems] = useState<ActionItem[]>([])
  const [mode, setMode] = useState<'' | 'approve' | 'report'>('')
  const [passcode, setPass] = useState(getPasscode)
  const [flooded, setFlooded] = useState(true)
  const [depth, setDepth] = useState('')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('')

  const load = (signal?: AbortSignal) =>
    listActions(city, signal)
      .then((all) => setItems(all.filter((i) => i.spotId === spotId)))
      .catch(() => {})
  useEffect(() => {
    const ac = new AbortController()
    load(ac.signal)
    return () => ac.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [city, spotId])

  if (!API.actions) return null

  const submit = async (approved?: boolean) => {
    setStatus('Saving…')
    try {
      setPasscode(passcode)
      if (approved !== undefined) await recordAction({ city, spotId, passcode, kind: 'approval', approved, note })
      else await recordAction({ city, spotId, passcode, kind: 'observation', flooded, depthCm: depth ? Number(depth) : undefined, date: today() })
      setStatus('Saved.')
      setMode('')
      setNote('')
      setDepth('')
      load()
    } catch (e) {
      setStatus((e as Error).message)
    }
  }

  return (
    <div className="fix-block">
      <span className="fix-step">
        <ClipboardText size={14} weight="fill" /> Officer log
      </span>
      {items.length > 0 && (
        <ul className="action-log">
          {items.slice(0, 5).map((i) => (
            <li key={i.sk}>
              <span className="mono">{(i.date ?? i.recordedAt).slice(0, 10)}</span>{' '}
              {i.kind === 'approval'
                ? `Action ${i.approved ? 'approved' : 'declined'}${i.note ? `: ${i.note}` : ''}`
                : `Reported ${i.flooded ? 'flooded' : 'not flooded'}${i.depthCm != null && i.depthCm !== '' ? `, about ${i.depthCm} cm` : ''}`}
            </li>
          ))}
        </ul>
      )}
      <p className="ai-label">Reports from officers, not measurements by this system.</p>
      <div className="action-buttons">
        {action && (
          <button className="btn" onClick={() => setMode(mode === 'approve' ? '' : 'approve')}>
            <Bell size={14} /> Approve action
          </button>
        )}
        <button className="btn" onClick={() => setMode(mode === 'report' ? '' : 'report')}>
          Report what happened
        </button>
      </div>
      {mode && (
        <form
          className="action-form"
          onSubmit={(e) => {
            e.preventDefault()
            if (mode === 'approve') return
          }}
        >
          <input type="password" placeholder="Officer passcode" value={passcode} onChange={(e) => setPass(e.target.value)} autoComplete="off" />
          {mode === 'approve' ? (
            <>
              <p>Tomorrow's suggested action: {action}.</p>
              <input type="text" placeholder="Note (optional)" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
              <div className="action-buttons">
                <button type="button" className="btn btn-primary" onClick={() => submit(true)}>
                  Approve
                </button>
                <button type="button" className="btn" onClick={() => submit(false)}>
                  Decline
                </button>
              </div>
            </>
          ) : (
            <>
              <label>
                <input type="checkbox" checked={flooded} onChange={(e) => setFlooded(e.target.checked)} /> It flooded
              </label>
              <input type="number" min={0} max={300} placeholder="Depth in cm (optional)" value={depth} onChange={(e) => setDepth(e.target.value)} />
              <button type="button" className="btn btn-primary" onClick={() => submit()}>
                Save report
              </button>
            </>
          )}
        </form>
      )}
      {status && <p className="ai-label">{status}</p>}
    </div>
  )
}
