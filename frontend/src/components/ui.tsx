import type { ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>
}

export function Label({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`label ${className}`}>{children}</div>
}

const tones = {
  neutral: 'border-line text-muted',
  ok: 'border-ok/25 bg-ok/[0.07] text-ok/90',
  warn: 'border-warn/25 bg-warn/[0.07] text-warn/90',
  bad: 'border-bad/25 bg-bad/[0.07] text-bad/90',
  fg: 'border-[#3a3a3a] text-fg',
}
export type Tone = keyof typeof tones

export function Badge({ children, tone = 'neutral', title }: { children: ReactNode; tone?: Tone; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 font-mono text-[10.5px] uppercase tracking-wider ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <Label>{eyebrow}</Label>
        <h1 className="mt-1.5 text-xl font-medium tracking-tight">{title}</h1>
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
}

export function Loading({ text = 'Loading' }: { text?: string }) {
  return <div className="label py-10 text-center">{text}…</div>
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="fade-in flex flex-wrap items-center justify-between gap-3 rounded-xl border border-bad/25 bg-bad/[0.05] px-4 py-3 text-sm text-bad/90">
      <span className="font-mono text-xs">Error · {error}</span>
      {onRetry && <button className="btn text-fg" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card fade-in px-6 py-10 text-center">
      <div className="text-sm">{title}</div>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  )
}

export function Score({ value, label }: { value: number; label?: string }) {
  return (
    <span className="font-mono text-xs text-muted">
      {label && <span className="mr-1 uppercase tracking-wider">{label}</span>}
      <span className="text-fg">{value.toFixed(2)}</span>
    </span>
  )
}

export function Bar({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100))
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-[#1f1f1f]">
      <div className="h-full rounded-full bg-fg/70" style={{ width: `${pct}%` }} />
    </div>
  )
}

export function SeedTag({ seed }: { seed: boolean }) {
  return seed ? <Badge title="Synthetic, clearly labelled demo record">Demo data</Badge> : <Badge tone="fg">Real</Badge>
}

export function fmtTime(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
