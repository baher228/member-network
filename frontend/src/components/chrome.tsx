import { useEffect, useState } from 'react'
import { api, type Health, type MemberStats } from '../api'
import { useSession } from '../session'
import { Badge, fmtTime } from './ui'

export function MemberPicker() {
  const { memberId, setMemberId } = useSession()
  const [members, setMembers] = useState<MemberStats[]>([])
  useEffect(() => {
    api.members().then((m) => {
      setMembers(m)
      if (memberId == null && m.length) setMemberId(m[0].id)
    }).catch(() => setMembers([]))
  }, [memberId, setMemberId])
  return (
    <label className="flex min-w-0 items-center gap-2">
      <span className="label">Viewing as</span>
      <select
        className="input min-w-0 flex-1 py-1.5 sm:w-56 sm:flex-none"
        value={memberId ?? ''}
        onChange={(e) => setMemberId(e.target.value ? Number(e.target.value) : null)}
      >
        {members.length === 0 && <option value="">No members</option>}
        {members.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}{m.is_seed ? ' · demo' : ''}
          </option>
        ))}
      </select>
    </label>
  )
}

export function HealthBar() {
  const [h, setH] = useState<Health | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    const load = () => api.health().then((x) => { setH(x); setErr(null) }).catch((e) => setErr(String(e.message ?? e)))
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="border-b border-line">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-2 sm:px-6">
        {err && <Badge tone="bad">API unreachable · {err}</Badge>}
        {h && (
          <>
            <Badge tone={h.db ? 'ok' : 'bad'}>DB {h.db ? 'connected' : 'down'}</Badge>
            <LlmBadge llm={h.llm} />
            <span className="label">{h.n_members} members · {h.n_interactions} interactions</span>
            {h.scheduler_next_run && <span className="label sm:ml-auto">Next weekly run {fmtTime(h.scheduler_next_run)}</span>}
          </>
        )}
      </div>
    </div>
  )
}

function LlmBadge({ llm }: { llm: Health['llm'] }) {
  const name = llm.provider === 'cursor' ? `${prettyModel(llm.model)} via Cursor` : llm.provider === 'grok' ? 'Grok' : 'Gemini'
  const last = llm.last_call
  const state = llm.state ?? (!llm.available ? 'unavailable' : last ? (last.ok ? 'working' : 'unavailable') : 'not_checked')
  if (state === 'working') return <Badge tone="ok" title={last ? `Last successful call ${fmtTime(last.at)}` : undefined}>{name} working</Badge>
  if (state === 'not_checked') return <Badge title="Key configured; no generation call yet">{name} · not checked yet</Badge>
  const why = !llm.available ? 'no key' : last?.http_status === 402 ? '402 credits depleted' : last?.http_status ? `HTTP ${last.http_status}` : 'call failed'
  return <Badge tone="warn" title={last?.error ?? llm.reason ?? undefined}>LLM unavailable · {why} – rule-only reasoning</Badge>
}

function prettyModel(m: string | null) {
  if (!m) return 'LLM'
  const g = m.match(/(gemini|grok|claude|gpt)-(\d+(?:\.\d+)?)(?:-(flash|pro|sonnet|opus|mini))?/i)
  if (!g) return m
  const cap = (x: string) => (x.toLowerCase() === 'gpt' ? 'GPT' : x[0].toUpperCase() + x.slice(1).toLowerCase())
  return [cap(g[1]), g[2], g[3] && cap(g[3])].filter(Boolean).join(' ')
}
