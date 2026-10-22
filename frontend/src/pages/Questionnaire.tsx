import { useState, type FormEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Member } from '../api'
import { useSession } from '../session'
import { Card, ErrorBox, Label, PageHeader } from '../components/ui'

const empty = {
  name: '', handle: '', github: '', devpost: '', builds: '', wants: '', speaker_topics: '',
  consent_intros: true, consent_speaker: false,
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <Label>{label}</Label>
      <div className="mt-1.5">{children}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </label>
  )
}

export default function Questionnaire() {
  const [f, setF] = useState(empty)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<Member | null>(null)
  const { setMemberId } = useSession()
  const nav = useNavigate()
  const set = (k: keyof typeof empty) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const blank = (s: string) => (s.trim() ? s.trim() : null)
      const m = await api.createMember({
        ...f, name: f.name.trim(), builds: f.builds.trim(), wants: f.wants.trim(), speaker_topics: f.speaker_topics.trim(),
        handle: blank(f.handle), github: blank(f.github.replace(/^@/, '')), devpost: blank(f.devpost.replace(/^@/, '')),
      })
      setSaved(m)
      setMemberId(m.id)
      setF(empty)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader eyebrow="Opt-in · 2 minutes" title="Tell the community what you build" />
      {saved && (
        <div className="fade-in mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-ok/25 bg-ok/[0.05] px-4 py-3 text-sm">
          <span>Thanks {saved.name} — you're in. Your answers are stored with your consent choices.</span>
          <button className="btn" onClick={() => nav('/for-you')}>See who to meet →</button>
        </div>
      )}
      {error && <div className="mb-4"><ErrorBox error={error} /></div>}
      <Card className="p-5 sm:p-6">
        <form onSubmit={submit} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name"><input required className="input" value={f.name} onChange={set('name')} placeholder="Ada Lovelace" /></Field>
            <Field label="Handle" hint="Discord / X / Telegram"><input className="input" value={f.handle} onChange={set('handle')} placeholder="@ada" /></Field>
            <Field label="GitHub username" hint="Used for public evidence (repos, stars)"><input className="input font-mono" value={f.github} onChange={set('github')} placeholder="octocat" /></Field>
            <Field label="Devpost username"><input className="input font-mono" value={f.devpost} onChange={set('devpost')} placeholder="ada" /></Field>
          </div>
          <Field label="What do you build?"><textarea required rows={3} className="input" value={f.builds} onChange={set('builds')} placeholder="Voice agents for customer support, built on Whisper + Grok" /></Field>
          <Field label="What do you want help with / who do you want to meet?"><textarea required rows={3} className="input" value={f.wants} onChange={set('wants')} placeholder="Someone who knows payments infra; a designer for onboarding" /></Field>
          <Field label="Topics you could speak on" hint="Comma-separated. Leave blank if none."><input className="input" value={f.speaker_topics} onChange={set('speaker_topics')} placeholder="speech recognition, evals" /></Field>
          <div className="space-y-2 rounded-lg border border-line p-4">
            <Label>Consent</Label>
            <label className="flex items-start gap-3 text-sm">
              <input type="checkbox" className="mt-0.5 accent-[#ededed]" checked={f.consent_intros} onChange={(e) => setF({ ...f, consent_intros: e.target.checked })} />
              <span>Suggest me for introductions to other members (max one a week, double opt-in).</span>
            </label>
            <label className="flex items-start gap-3 text-sm">
              <input type="checkbox" className="mt-0.5 accent-[#ededed]" checked={f.consent_speaker} onChange={(e) => setF({ ...f, consent_speaker: e.target.checked })} />
              <span>Suggest me to organisers as a speaker on my topics, with my public GitHub/Devpost as evidence.</span>
            </label>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted">You can withdraw consent any time; we never share your answers outside this community.</span>
            <button disabled={saving} className="btn-primary">{saving ? 'Saving…' : 'Join'}</button>
          </div>
        </form>
      </Card>
    </div>
  )
}
