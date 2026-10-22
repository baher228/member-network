import type { Reason } from '../api'
import { Badge } from './ui'

const kindLabel: Record<Reason['kind'], string> = { cf: 'Liked-by-similar', content: 'Builds ↔ wants', popularity: 'Popular' }

export function Reasons({ reasons }: { reasons: Reason[] }) {
  if (!reasons.length) return <div className="text-sm text-muted">No structured reasons.</div>
  return (
    <ul className="space-y-2">
      {reasons.map((r, i) => (
        <li key={i} className="flex flex-col items-start gap-1">
          <div><Badge>{kindLabel[r.kind] ?? r.kind} · {r.weight.toFixed(2)}</Badge></div>
          <span className="text-sm leading-relaxed text-fg/90">{r.text}</span>
        </li>
      ))}
    </ul>
  )
}
