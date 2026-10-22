import { useState } from 'react'
import { api, type ThreadAnalysis, type ThreadResult } from '../api'
import { useAsync } from '../useAsync'
import { Badge, Card, Empty, ErrorBox, Label, Loading, PageHeader, fmtTime } from '../components/ui'

function ThreadCard({ t }: { t: ThreadResult }) {
  return (
    <Card className={`fade-in p-4 ${t.worth_reviving ? '' : 'opacity-70'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium">{t.title}</div>
          <div className="mt-0.5 font-mono text-xs text-muted">
            {t.n_messages} msgs · {t.n_participants} people · silent {t.days_silent.toFixed(1)}d · last {fmtTime(t.last_message_at)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-muted">score {t.score.toFixed(2)}</span>
          {t.worth_reviving ? <Badge tone="warn">Worth reviving</Badge> : <Badge>Leave</Badge>}
          <Badge tone={t.status === 'failed' ? 'bad' : 'neutral'}>{t.status}</Badge>
        </div>
      </div>
      {t.reasons.length > 0 && <ul className="mt-3 space-y-1 text-sm text-fg/90">{t.reasons.map((r, i) => <li key={i}>· {r}</li>)}</ul>}
      {t.worth_reviving && (
        <div className="mt-3">
          {t.nudge
            ? <div className="rounded-lg border border-line bg-bg p-3 text-sm leading-relaxed whitespace-pre-wrap">{t.nudge}<div className="label mt-2">{t.llm_used ? 'Drafted by the LLM from the facts above' : 'Rule-based'}</div></div>
            : <div className="rounded-lg border border-dashed border-line p-3 text-sm text-muted">No nudge drafted — LLM unavailable, rule-only reasoning.</div>}
        </div>
      )}
      {t.error && <div className="mt-2 font-mono text-xs text-bad/90">Error · {t.error}</div>}
    </Card>
  )
}

export default function Threads() {
  const runs = useAsync(() => api.threadRuns(), [])
  const [text, setText] = useState('')
  const [now, setNow] = useState<string | undefined>()
  const [res, setRes] = useState<ThreadAnalysis | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [onlyRevive, setOnlyRevive] = useState(true)

  async function loadSample() {
    setErr(null)
    try { const s = await api.threadSample(); setText(s.log_text); setNow(s.suggested_now) } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }
  async function analyze() {
    setBusy(true); setErr(null)
    try { setRes(await api.analyzeThreads(text, now)); void runs.reload() } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
  }
  const threads = (res?.threads ?? []).filter((t) => !onlyRevive || t.worth_reviving)

  return (
    <div>
      <PageHeader eyebrow="Thread reviver" title="Spot dead conversations worth restarting" />
      <Card className="mb-6 p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <Label>Exported chat log · Discord-style or WhatsApp export</Label>
          <button className="btn py-1 text-xs" onClick={loadSample}>Load synthetic sample</button>
        </div>
        <textarea className="input h-40 font-mono text-xs" value={text} onChange={(e) => { setText(e.target.value); setNow(undefined) }}
          placeholder={'2026-10-01 18:04 | #voice-agents | Maya R.: anyone want to pair on diarisation?\n[01/10/2026, 18:04] Ben K.: …'} />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-muted">{now ? `Evaluated as of ${fmtTime(now)} (fixed for the sample so the demo is reproducible)` : 'Evaluated as of now'} · nothing is posted to any chat</span>
          <button disabled={busy || !text.trim()} className="btn-primary" onClick={analyze}>{busy ? 'Analysing…' : 'Analyse threads'}</button>
        </div>
      </Card>
      {err && <div className="mb-4"><ErrorBox error={err} /></div>}
      {busy && <Loading text="Parsing and scoring threads" />}
      {!busy && !res && !err && <Empty title="Paste an export or load the sample">Rules in code decide which threads died with an open question or offer; the LLM only drafts the nudge.</Empty>}
      {res && !busy && (
        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge>{res.threads.length} threads</Badge>
              <Badge tone="warn">{res.threads.filter((t) => t.worth_reviving).length} worth reviving</Badge>
              <Badge>{res.parsed_lines} lines parsed · {res.skipped_lines} skipped</Badge>
              <button className={`btn ml-auto py-1 text-xs ${onlyRevive ? 'bg-hover text-fg' : 'text-muted'}`} onClick={() => setOnlyRevive(!onlyRevive)}>{onlyRevive ? 'Showing revivable' : 'Showing all'}</button>
            </div>
            {threads.length === 0 && <Empty title="No threads to show" />}
            <div className="space-y-3">{threads.map((t) => <ThreadCard key={t.thread_id} t={t} />)}</div>
          </div>
          <div>
            <Label className="mb-2">Run #{res.run_id} log · what it tried</Label>
            <Card className="divide-y divide-line">
              {res.log.map((l, i) => (
                <div key={i} className="flex gap-2 px-3 py-2 text-xs">
                  <span className={`font-mono ${l.ok ? 'text-ok/80' : 'text-bad/90'}`}>{l.ok ? 'ok' : 'fail'}</span>
                  <div className="min-w-0"><div className="font-mono text-fg/90">{l.step}</div><div className="break-words text-muted">{l.detail}</div></div>
                </div>
              ))}
            </Card>
            {runs.data && runs.data.length > 0 && (
              <div className="mt-4">
                <Label className="mb-2">Previous runs</Label>
                <div className="space-y-1">{runs.data.slice(0, 8).map((r) => (
                  <div key={r.id} className="flex justify-between font-mono text-[11px] text-muted"><span>#{r.id} · {fmtTime(r.created_at)}</span><span>{r.n_revive}/{r.n_threads} · LLM {r.llm_status}</span></div>
                ))}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
