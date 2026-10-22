export type Member = {
  id: number; name: string; handle: string | null; github: string | null; devpost: string | null
  builds: string; wants: string; speaker_topics: string; consent_intros: boolean; consent_speaker: boolean
  is_seed: boolean; created_at: string
}
export type MemberStats = Member & { likes_given: number; likes_received: number; connections: number; isolated: boolean }
export type Reason = { kind: 'cf' | 'content' | 'popularity'; text: string; weight: number; evidence: Record<string, unknown> }
export type Recommendation = { member: Member; score: number; cf_score: number; content_score: number; reasons: Reason[] }
export type RecResponse = {
  member_id: number
  model: { n_interactions: number; member_interactions: number; cf_weight: number; content_weight: number; embedder: string }
  items: Recommendation[]
}
export type IntroStatus = 'drafted' | 'sent' | 'accepted' | 'declined' | 'failed'
export type Intro = {
  id: number; run_id: number; member_id: number; member_name: string; target_id: number; target_name: string
  score: number; reasons: Reason[]; message: string | null; llm_used: boolean; status: IntroStatus
  error: string | null; created_at: string; updated_at: string
}
export type IntroRun = {
  id: number; trigger: 'manual' | 'scheduled'; started_at: string; finished_at: string | null
  n_members: number; n_drafted: number; n_failed: number; n_skipped: number
  llm_status: 'available' | 'unavailable' | 'partial'; notes: string | null
}
export type Evidence = { source: string; title: string; url: string | null; detail: string | null; live: boolean; fetched_at: string | null }
export type SpeakerCandidate = {
  kind: 'member' | 'external'; member_id: number | null; name: string; handle: string | null
  score: number; match_reasons: string[]; evidence: Evidence[]
}
export type SourceStatus = { source: string; status: 'live' | 'cached' | 'failed' | 'skipped'; error: string | null }
export type SpeakerResponse = { topic: string; items: SpeakerCandidate[]; sources: SourceStatus[] }
export type EvalResponse = {
  computed_at: string; holdout_fraction: number; k: number; n_test_users: number; n_holdout: number
  results: { model: string; hit_rate: number; precision: number; hit_rate_std?: number; precision_std?: number; slice?: 'all' | 'cold-start' }[]; notes: string[]
}
export type Health = {
  db: boolean; llm: { provider?: 'gemini' | 'grok'; state?: 'not_checked' | 'working' | 'unavailable'; last_call?: { ok: boolean; at: string; http_status: number | null; error: string | null } | null; available: boolean; model: string | null; reason: string | null }
  n_members: number; n_interactions: number; scheduler_next_run?: string | null
}
export type GraphResponse = {
  nodes: { id: number; name: string; degree: number; isolated: boolean; is_seed: boolean }[]
  edges: { source: number; target: number; kind: string }[]
  metrics: { density: number; n_isolated: number; avg_degree: number }
}

export type ThreadResult = {
  thread_id: string; title: string; last_message_at: string; n_messages: number; n_participants: number
  days_silent: number; ended_with_question: boolean; unanswered_by: string | null; worth_reviving: boolean
  score: number; reasons: string[]; nudge: string | null; llm_used: boolean
  status: 'drafted' | 'skipped' | 'failed'; error: string | null
}
export type ThreadAnalysis = {
  run_id: number; parsed_lines: number; skipped_lines: number; threads: ThreadResult[]
  log: { step: string; ok: boolean; detail: string }[]
}
export type ThreadRun = { id: number; created_at: string; n_threads: number; n_revive: number; llm_status: string }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* non-JSON error body */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}
const post = <T,>(path: string, body?: unknown) => req<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) })

export const api = {
  health: () => req<Health>('/health'),
  members: () => req<MemberStats[]>('/members'),
  member: (id: number) => req<Member>(`/members/${id}`),
  createMember: (m: Omit<Member, 'id' | 'is_seed' | 'created_at'>) => post<Member>('/members', m),
  recommendations: (id: number, k = 10) => req<RecResponse>(`/members/${id}/recommendations?k=${k}`),
  interact: (member_id: number, target_id: number, kind: 'like' | 'pass') =>
    post<{ ok: boolean; n_interactions: number }>('/interactions', { member_id, target_id, kind }),
  runIntros: () => post<{ run: IntroRun; intros: Intro[] }>('/intros/run', { trigger: 'manual' }),
  runs: () => req<IntroRun[]>('/intros/runs'),
  intros: (runId?: number) => req<Intro[]>(`/intros${runId ? `?run_id=${runId}` : ''}`),
  respond: (id: number, response: 'accepted' | 'declined') =>
    post<{ intro: Intro; n_interactions: number }>(`/intros/${id}/respond`, { response }),
  speakers: (topic: string, external = true) =>
    req<SpeakerResponse>(`/speakers?topic=${encodeURIComponent(topic)}&include_external=${external}`),
  evaluation: () => req<EvalResponse>('/eval'),
  runEval: () => post<EvalResponse>('/eval/run'),
  threadSample: () => req<{ log_text: string; suggested_now?: string }>('/threads/sample'),
  analyzeThreads: (log_text: string, now?: string) => post<ThreadAnalysis>('/threads/analyze', now ? { log_text, now } : { log_text }),
  threadRuns: () => req<ThreadRun[]>('/threads/runs'),
  graph: () => req<GraphResponse>('/graph'),
  resetDemo: () => post<Record<string, unknown>>('/demo/reset'),
}
