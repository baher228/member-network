import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useSession } from '../session'
import { useAsync } from '../useAsync'
import { Badge, Card, ErrorBox, Label, Loading, PageHeader, SeedTag } from '../components/ui'
import GraphView from '../components/GraphView'

export default function Members() {
  const { data, error, loading, reload } = useAsync(() => api.members(), [])
  const graph = useAsync(() => api.graph(), [])
  const [q, setQ] = useState('')
  const [onlyIsolated, setOnlyIsolated] = useState(false)
  const { setMemberId } = useSession()
  const nav = useNavigate()
  const [resetting, setResetting] = useState(false)
  const [resetMsg, setResetMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const reset = async () => {
    if (!confirm('Restore the seeded demo state? Non-seed members and their data are kept.')) return
    setResetting(true); setResetMsg(null)
    try {
      const r = await api.resetDemo()
      const parts = Object.entries(r).filter(([, v]) => typeof v === 'number').map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`)
      setResetMsg({ ok: true, text: `Demo reset · ${parts.join(' · ')}` })
      reload(); graph.reload()
    } catch (e) {
      setResetMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally { setResetting(false) }
  }
  const rows = useMemo(() => (data ?? []).filter((m) =>
    (!onlyIsolated || m.isolated) &&
    `${m.name} ${m.builds} ${m.wants} ${m.speaker_topics}`.toLowerCase().includes(q.toLowerCase())), [data, q, onlyIsolated])

  return (
    <div>
      <PageHeader eyebrow="Lead view" title="Members">
        <input className="input w-full sm:w-56" placeholder="Search builds, wants, topics" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className={`btn ${onlyIsolated ? 'bg-hover text-fg' : 'text-muted'}`} onClick={() => setOnlyIsolated(!onlyIsolated)}>Isolated only</button>
        <button className="btn text-muted" disabled={resetting} onClick={reset}>{resetting ? 'Resetting…' : 'Reset demo'}</button>
      </PageHeader>
      {resetMsg && (resetMsg.ok
        ? <div className="mb-4 font-mono text-xs text-muted">{resetMsg.text}</div>
        : <div className="mb-4"><ErrorBox error={resetMsg.text} /></div>)}
      {graph.data && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Members', graph.data.metrics.n_not_opted_in ? `${graph.data.metrics.n_opted_in} opted in · +${graph.data.metrics.n_not_opted_in} Luma` : String(graph.data.nodes.length)],
            ['Connections', String(graph.data.edges.length)],
            ['Avg degree', graph.data.metrics.avg_degree.toFixed(1)],
            ['Isolated', String(graph.data.metrics.n_isolated)],
          ].map(([k, v]) => (
            <Card key={k} className="p-4"><Label>{k}</Label><div className="mt-1 font-mono text-xl">{v}</div></Card>
          ))}
        </div>
      )}
      {graph.data && (
        <div className="mb-6">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <Label>Member graph · likes &amp; accepted intros · muted nodes: not opted in</Label>
            <span className="label">density {graph.data.metrics.density.toFixed(3)} · <span className="text-warn/80">●</span> isolated · <span className="text-ok/80">—</span> accepted intro</span>
          </div>
          <GraphView graph={graph.data} onSelect={(id) => { setMemberId(id); nav('/for-you') }} />
        </div>
      )}
      {graph.error && <div className="mb-4"><ErrorBox error={graph.error} onRetry={graph.reload} /></div>}
      {loading && !data && <Loading />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-line text-left">
                {['Member', 'Builds', 'Wants', 'Likes in/out', 'Conn.', 'Consent', ''].map((h) => <th key={h} className="label px-4 py-2.5 font-normal">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} className="border-b border-line/60 align-top transition-colors duration-150 last:border-0 hover:bg-hover">
                  <td className="px-4 py-3">
                    <div className="font-medium">{m.name}</div>
                    <div className="mt-1 flex flex-wrap gap-1"><SeedTag seed={m.is_seed} />{m.opted_in === false ? <Badge>Not opted in · Luma</Badge> : m.isolated && <Badge tone="warn">Isolated</Badge>}</div>
                  </td>
                  <td className="max-w-[240px] px-4 py-3 text-fg/85">{m.builds}</td>
                  <td className="max-w-[240px] px-4 py-3 text-fg/85">{m.wants}</td>
                  <td className="px-4 py-3 font-mono text-xs">{m.likes_received} / {m.likes_given}</td>
                  <td className="px-4 py-3 font-mono text-xs">{m.connections}</td>
                  <td className="px-4 py-3"><div className="flex flex-col gap-1">
                    <Badge tone={m.consent_intros ? 'ok' : 'neutral'}>Intros {m.consent_intros ? 'yes' : 'no'}</Badge>
                    <Badge tone={m.consent_speaker ? 'ok' : 'neutral'}>Speaker {m.consent_speaker ? 'yes' : 'no'}</Badge>
                  </div></td>
                  <td className="px-4 py-3"><button disabled={m.opted_in === false} className="btn whitespace-nowrap py-1 text-xs disabled:opacity-30" onClick={() => { setMemberId(m.id); nav('/for-you') }}>View as</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <div className="p-6 text-center text-sm text-muted">No members match.</div>}
        </Card>
      )}
    </div>
  )
}
