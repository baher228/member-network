import { useState } from 'react'
import { api, type Intro, type IntroRun, type IntroStatus } from '../api'
import { useAsync } from '../useAsync'
import { Badge, Card, Empty, ErrorBox, Label, Loading, PageHeader, fmtTime, type Tone } from '../components/ui'
import { Reasons } from '../components/reasons'

const statusTone: Record<IntroStatus, Tone> = { drafted: 'neutral', sent: 'fg', accepted: 'ok', declined: 'bad', failed: 'bad' }

function RunRow({ run, active, onClick }: { run: IntroRun; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors duration-150 ${active ? 'border-[#444] bg-hover' : 'border-line hover:bg-hover'}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs">Run #{run.id}</span>
        <Badge>{run.trigger}</Badge>
      </div>
      <div className="mt-1 font-mono text-[11px] text-muted">{fmtTime(run.started_at)}</div>
      <div className="mt-2 flex flex-wrap gap-1">
        <Badge>{run.n_drafted} drafted</Badge>
        {run.n_failed > 0 && <Badge tone="bad">{run.n_failed} failed</Badge>}
        {run.n_skipped > 0 && <Badge>{run.n_skipped} skipped</Badge>}
        <Badge tone={run.llm_status === 'available' ? 'ok' : 'warn'}>LLM {run.llm_status}</Badge>
      </div>
    </button>
  )
}

function IntroCard({ intro, onRespond, busy }: { intro: Intro; onRespond: (r: 'accepted' | 'declined') => void; busy: boolean }) {
  const open = intro.status === 'drafted' || intro.status === 'sent'
  return (
    <Card className="fade-in p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm"><span className="font-medium">{intro.member_name}</span><span className="text-muted"> → </span><span className="font-medium">{intro.target_name}</span></div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-muted">score {intro.score.toFixed(2)}</span>
          <Badge tone={statusTone[intro.status]}>{intro.status}</Badge>
        </div>
      </div>
      <div className="mt-3">
        {intro.message
          ? <div className="rounded-lg border border-line bg-bg p-3 text-sm leading-relaxed whitespace-pre-wrap">{intro.message}<div className="label mt-2">{intro.llm_used ? 'Written by the LLM from the reasons below' : 'Rule-based'}</div></div>
          : <div className="rounded-lg border border-dashed border-line p-3 text-sm text-muted">No message — LLM unavailable, rule-only reasoning. The structured reasons below are what the intro is based on.</div>}
      </div>
      {intro.error && <div className="mt-2 font-mono text-xs text-bad/90">Error · {intro.error}</div>}
      <details className="mt-3">
        <summary className="label cursor-pointer select-none hover:text-fg">Reasons</summary>
        <div className="mt-2"><Reasons reasons={intro.reasons} /></div>
      </details>
      {open && (
        <div className="mt-3 flex gap-2">
          <button disabled={busy} className="btn" onClick={() => onRespond('declined')}>Decline</button>
          <button disabled={busy} className="btn-primary" onClick={() => onRespond('accepted')}>Accept intro</button>
        </div>
      )}
    </Card>
  )
}

export default function Intros() {
  const runs = useAsync(() => api.runs(), [])
  const [runId, setRunId] = useState<number | null>(null)
  const activeRun = runId ?? runs.data?.[0]?.id ?? null
  const intros = useAsync(() => (activeRun == null ? Promise.resolve([] as Intro[]) : api.intros(activeRun)), [activeRun])
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [filter, setFilter] = useState<IntroStatus | 'all'>('all')

  async function run() {
    setRunning(true); setErr(null)
    try {
      const res = await api.runIntros()
      await runs.reload()
      setRunId(res.run.id)
      setNote(`Run #${res.run.id}: ${res.run.n_drafted} intros drafted, ${res.run.n_failed} failed, ${res.run.n_skipped} skipped`)
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setRunning(false) }
  }
  async function respond(i: Intro, r: 'accepted' | 'declined') {
    setBusy(i.id); setErr(null)
    try {
      const res = await api.respond(i.id, r)
      intros.setData((intros.data ?? []).map((x) => (x.id === i.id ? res.intro : x)))
      setNote(`${i.member_name} ${r} intro to ${i.target_name} · model updated from ${res.n_interactions} interactions`)
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setBusy(null) }
  }

  const list = (intros.data ?? []).filter((i) => filter === 'all' || i.status === filter)
  const counts = (intros.data ?? []).reduce<Record<string, number>>((a, i) => ({ ...a, [i.status]: (a[i.status] ?? 0) + 1 }), {})

  return (
    <div>
      <PageHeader eyebrow="Weekly intro bot" title="One introduction per member, every week">
        <button disabled={running} className="btn-primary" onClick={run}>{running ? 'Running…' : 'Run weekly intros now'}</button>
      </PageHeader>
      {note && <div className="label mb-4 fade-in text-fg/80">{note}</div>}
      {err && <div className="mb-4"><ErrorBox error={err} /></div>}
      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <div>
          <Label className="mb-2">Run log</Label>
          {runs.loading && !runs.data && <Loading />}
          {runs.error && <ErrorBox error={runs.error} onRetry={runs.reload} />}
          {runs.data?.length === 0 && <div className="text-sm text-muted">No runs yet. The scheduler runs weekly; trigger one now.</div>}
          <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
            {runs.data?.map((r) => <div key={r.id} className="min-w-[210px] lg:min-w-0"><RunRow run={r} active={r.id === activeRun} onClick={() => setRunId(r.id)} /></div>)}
          </div>
          {runs.data?.find((r) => r.id === activeRun)?.notes && <p className="mt-3 text-xs text-muted">{runs.data.find((r) => r.id === activeRun)?.notes}</p>}
        </div>
        <div>
          <div className="mb-3 flex flex-wrap gap-1">
            {(['all', 'drafted', 'sent', 'accepted', 'declined', 'failed'] as const).map((s) => (
              <button key={s} onClick={() => setFilter(s)} className={`rounded-md border px-2 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors duration-150 ${filter === s ? 'border-[#444] bg-hover text-fg' : 'border-line text-muted hover:text-fg'}`}>
                {s} {s === 'all' ? intros.data?.length ?? 0 : counts[s] ?? 0}
              </button>
            ))}
          </div>
          {intros.loading && !intros.data && <Loading />}
          {intros.error && <ErrorBox error={intros.error} onRetry={intros.reload} />}
          {intros.data && list.length === 0 && <Empty title={activeRun ? 'No intros match this filter' : 'No intro runs yet'} />}
          <div className="space-y-3">{list.map((i) => <IntroCard key={i.id} intro={i} busy={busy === i.id} onRespond={(r) => respond(i, r)} />)}</div>
        </div>
      </div>
    </div>
  )
}
