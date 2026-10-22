import { useState } from 'react'
import { api } from '../api'
import { useAsync } from '../useAsync'
import { Bar, Card, ErrorBox, Label, Loading, PageHeader, fmtTime } from '../components/ui'

const names: Record<string, string> = { popularity: 'Popularity baseline', cf: 'Collaborative filtering', content: 'Content (embeddings)', hybrid: 'Hybrid' }

export default function Evaluation() {
  const { data, error, loading, reload, setData } = useAsync(() => api.evaluation(), [])
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function rerun() {
    setRunning(true); setErr(null)
    try { setData(await api.runEval()) } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setRunning(false) }
  }
  const best = data ? Math.max(...data.results.map((r) => r.hit_rate)) : 0
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Offline evaluation · demo data" title="Does the recommender beat a baseline?">
        <button disabled={running} className="btn" onClick={rerun}>{running ? 'Computing…' : 'Recompute'}</button>
      </PageHeader>
      {err && <div className="mb-4"><ErrorBox error={err} /></div>}
      {loading && !data && <Loading text="Computing hold-out metrics" />}
      {error && <ErrorBox error={error} onRetry={reload} />}
      {data && (
        <>
          <Card className="mb-4 p-4 text-sm text-fg/85">
            Hold out {Math.round(data.holdout_fraction * 100)}% of each seed member's likes ({data.n_holdout} likes, {data.n_test_users} members), train on the rest, and check whether the held-out people appear in each model's top {data.k}. Synthetic data with planted cluster structure — useful for sanity, not a claim about real communities.
          </Card>
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead><tr className="border-b border-line text-left">
                {['Model', `Hit-rate@${data.k}`, '', `Precision@${data.k}`].map((h, i) => <th key={i} className="label px-4 py-2.5 font-normal">{h}</th>)}
              </tr></thead>
              <tbody>
                {data.results.map((r) => (
                  <tr key={r.model} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-3">{names[r.model] ?? r.model}{r.hit_rate === best && <span className="label ml-2 text-ok/80">best</span>}</td>
                    <td className="px-4 py-3 font-mono">{r.hit_rate.toFixed(3)}</td>
                    <td className="w-40 px-4 py-3"><Bar value={r.hit_rate} /></td>
                    <td className="px-4 py-3 font-mono">{r.precision.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          {data.notes.length > 0 && (
            <div className="mt-4"><Label className="mb-2">Notes</Label><ul className="space-y-1 text-sm text-fg/85">{data.notes.map((n, i) => <li key={i}>· {n}</li>)}</ul></div>
          )}
          <div className="label mt-4">Computed {fmtTime(data.computed_at)} · CLI: python -m app.eval</div>
        </>
      )}
    </div>
  )
}
