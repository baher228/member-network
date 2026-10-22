import { useEffect, useMemo, useRef, useState } from 'react'

export type DropdownOption = { value: number; label: string; hint?: string }

export function Dropdown({ value, options, onChange, placeholder = 'Select', className = '' }: {
  value: number | null; options: DropdownOption[]; onChange: (v: number) => void; placeholder?: string; className?: string
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const filterRef = useRef<HTMLInputElement>(null)
  const current = options.find((o) => o.value === value)
  const shown = useMemo(() => options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase())), [options, q])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    filterRef.current?.focus()
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])
  useEffect(() => { if (!open) setQ('') }, [open])

  const pick = (v: number) => { onChange(v); setOpen(false) }

  return (
    <div ref={root} className={`relative ${className}`}>
      <button type="button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="input flex w-full items-center justify-between gap-2 py-1.5 text-left">
        <span className="truncate">{current ? current.label : placeholder}{current?.hint && <span className="text-muted"> · {current.hint}</span>}</span>
        <svg width="12" height="12" viewBox="0 0 12 12" className={`shrink-0 text-muted transition-transform duration-150 ${open ? 'rotate-180' : ''}`}><path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {open && (
        <div className="fade-in absolute right-0 z-50 mt-1 w-full min-w-56 overflow-hidden rounded-lg border border-line bg-card shadow-[0_8px_24px_rgba(0,0,0,.5)]">
          <div className="border-b border-line p-1.5">
            <input ref={filterRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type to filter"
              onKeyDown={(e) => { if (e.key === 'Enter' && shown[0]) pick(shown[0].value) }}
              className="w-full rounded-md bg-transparent px-2 py-1 text-sm text-fg outline-none placeholder:text-muted" />
          </div>
          <ul role="listbox" className="max-h-80 overflow-y-auto py-1">
            {shown.length === 0 && <li className="px-3 py-2 text-sm text-muted">No matches</li>}
            {shown.map((o) => (
              <li key={o.value} role="option" aria-selected={o.value === value}>
                <button type="button" onClick={() => pick(o.value)}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-fg hover:bg-hover">
                  <span className="w-3 shrink-0 text-fg">{o.value === value ? '✓' : ''}</span>
                  <span className="truncate">{o.label}{o.hint && <span className="text-muted"> · {o.hint}</span>}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
