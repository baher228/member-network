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
            {h.llm.available
              ? <Badge tone="ok">Grok · {h.llm.model}</Badge>
              : <Badge tone="warn" title={h.llm.reason ?? undefined}>LLM unavailable – rule-only reasoning</Badge>}
            <span className="label">{h.n_members} members · {h.n_interactions} interactions</span>
            {h.scheduler_next_run && <span className="label sm:ml-auto">Next weekly run {fmtTime(h.scheduler_next_run)}</span>}
          </>
        )}
      </div>
    </div>
  )
}
