import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { useAsync } from '../useAsync'
import { Card, ErrorBox, Label } from './ui'

export function CogneeCard() {
  const health = useAsync(api.health, [])
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [counts, setCounts] = useState<string | null>(null)
  const [busy, setBusy] = useState<'search' | 'sync' | null>(null)
  if (!health.data?.cognee?.enabled) return null

  async function ask(e: FormEvent) {
    e.preventDefault()
    if (!query.trim() || busy) return
    setBusy('search'); setAnswer(null); setError(null)
    try {
      const result = await api.cogneeSearch(query)
      if (result.status === 'failed') setError(result.error ?? 'Cognee request failed')
      else setAnswer(typeof result.answer === 'string' ? result.answer : JSON.stringify(result.answer, null, 2))
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy(null) }
  }

  async function sync() {
    setBusy('sync'); setError(null); setCounts(null)
    try {
      const result = await api.cogneeSync()
      setCounts(`${result.sent} sent · ${result.excluded} excluded (${result.not_opted_in_excluded} not opted in, ${result.no_consent_excluded} without consent)`)
      if (result.status === 'failed') setError(result.error ?? 'Cognee sync failed')
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy(null) }
  }

  return <Card className="mb-6 p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-medium">Ask the network · Cognee</h2>
      <button className="btn text-xs" disabled={busy !== null} onClick={() => void sync()}>{busy === 'sync' ? 'Syncing…' : 'Sync to Cognee'}</button>
    </div>
    <p className="mb-3 text-sm text-muted">Search opted-in, consenting members using Cognee’s knowledge graph.</p>
    <form className="flex flex-col gap-3 sm:flex-row" onSubmit={ask}>
      <input className="input flex-1" aria-label="Ask the network" value={query} onChange={e => setQuery(e.target.value)} placeholder="Who works on voice AI and could speak about it?" />
      <button className="btn-primary" disabled={busy !== null || !query.trim()}>{busy === 'search' ? 'Asking Cognee…' : 'Ask'}</button>
    </form>
    {counts && <p className="mt-3 font-mono text-xs text-muted" role="status">{counts}</p>}
    {busy && <p className="mt-3 text-sm text-muted" role="status">{busy === 'sync' ? 'Uploading consented profiles and building the graph…' : 'Searching the graph…'}</p>}
    {error && <div className="mt-3"><ErrorBox error={error} /></div>}
    {answer !== null && <div className="mt-4 border-t border-line pt-3"><Label>FROM COGNEE · GRAPH_COMPLETION</Label><div className="mt-2 whitespace-pre-wrap text-sm">{answer}</div></div>}
  </Card>
}
