import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Recommendation } from '../api'
import { useSession } from '../session'
import { useAsync } from '../useAsync'
import { Badge, Bar, Card, Empty, ErrorBox, Label, Loading, PageHeader, SeedTag } from '../components/ui'
import { Reasons } from '../components/reasons'

function RecCard({ r, onAct, busy }: { r: Recommendation; onAct: (kind: 'like' | 'pass') => void; busy: boolean }) {
  const m = r.member
  return (
    <Card className="fade-in flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{m.name}</span>
            <SeedTag seed={m.is_seed} />
          </div>
          <div className="mt-0.5 truncate font-mono text-xs text-muted">{[m.handle, m.github && `gh:${m.github}`].filter(Boolean).join(' · ') || 'no handles'}</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-lg leading-none">{r.score.toFixed(2)}</div>
          <Label className="mt-1">match</Label>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label>Builds</Label><p className="mt-1 text-sm text-fg/90">{m.builds}</p></div>
        <div><Label>Wants</Label><p className="mt-1 text-sm text-fg/90">{m.wants}</p></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><div className="mb-1 flex justify-between"><Label>Collaborative</Label><span className="font-mono text-xs">{r.cf_score.toFixed(2)}</span></div><Bar value={r.cf_score} /></div>
        <div><div className="mb-1 flex justify-between"><Label>Content</Label><span className="font-mono text-xs">{r.content_score.toFixed(2)}</span></div><Bar value={r.content_score} /></div>
      </div>
      <div className="border-t border-line pt-3"><Label className="mb-2">Why</Label><Reasons reasons={r.reasons} /></div>
      <div className="mt-auto flex gap-2">
        <button disabled={busy} className="btn flex-1" onClick={() => onAct('pass')}>Pass</button>
        <button disabled={busy} className="btn-primary flex-1" onClick={() => onAct('like')}>Like</button>
      </div>
    </Card>
  )
}

export default function ForYou() {
  const { memberId } = useSession()
  const { data, error, loading, reload } = useAsync(
    () => (memberId == null ? Promise.resolve(null) : api.recommendations(memberId, 9)), [memberId])
  const me = useAsync(() => (memberId == null ? Promise.resolve(null) : api.member(memberId)), [memberId])
  const [busy, setBusy] = useState<number | null>(null)
  const [actErr, setActErr] = useState<string | null>(null)
  const [lastAct, setLastAct] = useState<string | null>(null)
  const [rated, setRated] = useState<{ id: number; name: string; kind: 'like' | 'pass' }[]>([])
  useEffect(() => { setRated([]); setLastAct(null) }, [memberId])
  const ratedIds = new Set(rated.map((x) => x.id))
  const items = (data?.items ?? []).filter((r) => !ratedIds.has(r.member.id))

  async function act(r: Recommendation, kind: 'like' | 'pass') {
    if (memberId == null) return
    setBusy(r.member.id)
    setActErr(null)
    try {
      const res = await api.interact(memberId, r.member.id, kind)
      setRated((xs) => [...xs, { id: r.member.id, name: r.member.name, kind }])
      setLastAct(`${kind === 'like' ? 'Liked' : 'Passed'} ${r.member.name} · model updated from ${res.n_interactions} interactions`)
      await reload()
    } catch (e) {
      setActErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  if (memberId == null) return <Empty title="Pick a member">Use “Viewing as” above, or <Link className="underline" to="/join">fill the questionnaire</Link>.</Empty>

  return (
    <div>
      <PageHeader eyebrow="For you · hybrid recommender" title={me.data ? `People ${me.data.name.split(' ')[0]} should meet` : 'People you should meet'}>
        {data && (
          <>
            <Badge>{data.model.member_interactions} of your interactions</Badge>
            <Badge>CF {data.model.cf_weight.toFixed(2)} · content {data.model.content_weight.toFixed(2)}</Badge>
            <Badge title="Text embedding model">{data.model.embedder}</Badge>
          </>
        )}
      </PageHeader>
      {me.data && (
        <Card className="mb-6 grid gap-4 p-4 sm:grid-cols-2">
          <div><Label>You build</Label><p className="mt-1 text-sm">{me.data.builds}</p></div>
          <div><Label>You want</Label><p className="mt-1 text-sm">{me.data.wants}</p></div>
          {!me.data.consent_intros && <div className="sm:col-span-2"><Badge tone="warn">You haven't consented to intros — you won't appear in others' suggestions</Badge></div>}
        </Card>
      )}
      {lastAct && <div className="label mb-2 fade-in text-fg/80">{lastAct}</div>}
      {rated.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          <Label>Already rated</Label>
          {rated.map((x) => <Badge key={x.id} tone={x.kind === 'like' ? 'ok' : 'neutral'}>{x.kind === 'like' ? 'Liked' : 'Passed'} {x.name}</Badge>)}
        </div>
      )}
      {actErr && <div className="mb-4"><ErrorBox error={actErr} /></div>}
      {loading && !data && <Loading text="Scoring members" />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && items.length === 0 && <Empty title="No suggestions left">You've seen everyone who consented to intros.</Empty>}
      {data && items.length > 0 && (
        <div className={`grid gap-4 md:grid-cols-2 lg:grid-cols-3 ${loading ? 'opacity-60 transition-opacity' : ''}`}>
          {items.map((r) => <RecCard key={r.member.id} r={r} busy={busy === r.member.id} onAct={(k) => act(r, k)} />)}
        </div>
      )}
      <p className="mt-6 text-xs text-muted">
        Model updated from {data?.model.n_interactions ?? '—'} interactions across the community. Collaborative weight grows as you like more people; new members start content-only.
      </p>
    </div>
  )
}
