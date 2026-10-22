import { useState, type FormEvent } from 'react'
import { api, type SpeakerCandidate, type SpeakerResponse } from '../api'
import { Badge, Card, Empty, ErrorBox, Label, Loading, PageHeader, fmtTime } from '../components/ui'

const examples = ['voice agents', 'developer tools', 'climate tech', 'payments', 'community building']

function Candidate({ c, rank }: { c: SpeakerCandidate; rank: number }) {
  return (
    <Card className="fade-in p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-muted">{String(rank).padStart(2, '0')}</span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{c.name}</span>
              <Badge tone={c.kind === 'member' ? 'fg' : 'neutral'}>{c.kind === 'member' ? 'Member · consented' : 'Public London builder'}</Badge>
            </div>
            {c.handle && <div className="font-mono text-xs text-muted">{c.handle}</div>}
          </div>
        </div>
        <span className="font-mono text-sm">{c.score.toFixed(2)}</span>
      </div>
      {c.match_reasons.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-fg/90">{c.match_reasons.map((r, i) => <li key={i}>· {r}</li>)}</ul>
      )}
      <div className="mt-3 border-t border-line pt-3">
        <Label className="mb-2">Evidence</Label>
        {c.evidence.length === 0 && <div className="text-sm text-muted">No public evidence found.</div>}
        <ul className="space-y-1.5">
          {c.evidence.map((e, i) => (
            <li key={i} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-baseline sm:gap-2">
              <span className="flex shrink-0 gap-1"><Badge>{e.source}</Badge><Badge tone={e.live ? 'ok' : 'neutral'} title={e.fetched_at ? `fetched ${fmtTime(e.fetched_at)}` : undefined}>{e.live ? 'live' : 'cached'}</Badge></span>
              <span className="min-w-0">
                {e.url ? <a className="underline decoration-line underline-offset-2 hover:decoration-fg" href={e.url} target="_blank" rel="noreferrer">{e.title}</a> : e.title}
                {e.detail && <span className="text-muted"> — {e.detail}</span>}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

export default function Speakers() {
  const [topic, setTopic] = useState('')
  const [external, setExternal] = useState(true)
  const [data, setData] = useState<SpeakerResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function search(t: string) {
    if (!t.trim()) return
    setTopic(t); setLoading(true); setError(null)
    try { setData(await api.speakers(t.trim(), external)) } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setLoading(false) }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); void search(topic) }

  return (
    <div>
      <PageHeader eyebrow="Speaker finder" title="Who could speak on this topic?" />
      <Card className="mb-6 p-4">
        <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
          <input className="input flex-1" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. speech recognition for voice agents" />
          <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" className="accent-[#ededed]" checked={external} onChange={(e) => setExternal(e.target.checked)} />Include public London builders</label>
          <button disabled={loading || !topic.trim()} className="btn-primary">{loading ? 'Searching…' : 'Find speakers'}</button>
        </form>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {examples.map((x) => <button key={x} className="rounded-md border border-line px-2 py-0.5 text-xs text-muted transition-colors duration-150 hover:bg-hover hover:text-fg" onClick={() => void search(x)}>{x}</button>)}
        </div>
      </Card>
      {data && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <Label className="mr-1">Sources</Label>
          {data.sources.map((s) => (
            <Badge key={s.source} tone={s.status === 'live' ? 'ok' : s.status === 'failed' ? 'bad' : 'neutral'} title={s.error ?? undefined}>{s.source} · {s.status}</Badge>
          ))}
        </div>
      )}
      {data?.sources.some((s) => s.status === 'failed') && (
        <div className="mb-4 space-y-1 font-mono text-xs text-bad/80">{data.sources.filter((s) => s.error).map((s) => <div key={s.source}>{s.source}: {s.error}</div>)}</div>
      )}
      {loading && <Loading text="Fetching GitHub, Devpost, HN and Luma evidence" />}
      {error && <ErrorBox error={error} onRetry={() => void search(topic)} />}
      {!loading && !data && !error && <Empty title="Enter a topic">Members who consented to speaker suggestions are ranked first, with evidence from their public profiles.</Empty>}
      {!loading && data && data.items.length === 0 && <Empty title="No candidates found for this topic" />}
      {!loading && data && data.items.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">{data.items.map((c, i) => <Candidate key={`${c.kind}-${c.name}-${i}`} c={c} rank={i + 1} />)}</div>
      )}
    </div>
  )
}
