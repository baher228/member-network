import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { forceX, forceY } from 'd3-force-3d'
import type { GraphResponse } from '../api'

const esc = (t: string) => t.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

export default function GraphView({ graph, onSelect }: { graph: GraphResponse; onSelect?: (id: number) => void }) {
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800)
  const fg = useRef<ForceGraphMethods | undefined>(undefined)
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const fitted = useRef(false)
  useEffect(() => {
    const g = fg.current
    if (!g) return
    const pull = (n: unknown) => ((n as { isolated: boolean }).isolated ? 0.35 : 0.06)
    g.d3Force('x', forceX(0).strength(pull) as never)
    g.d3Force('y', forceY(0).strength(pull) as never)
    fitted.current = false
    g.d3ReheatSimulation()
  }, [graph])
  const fit = () => {
    if (fitted.current) return
    fitted.current = true
    fg.current?.zoomToFit(400, 24)
  }
  const data = useMemo(() => ({
    nodes: graph.nodes.map((n) => ({ ...n })),
    links: graph.edges.map((e) => ({ ...e })),
  }), [graph])
  return (
    <div ref={wrap} className="w-full overflow-hidden rounded-xl border border-line bg-card">
      <ForceGraph2D
        ref={fg}
        graphData={data}
        onEngineStop={fit}
        width={width}
        height={width < 500 ? 320 : 420}
        backgroundColor="#121212"
        cooldownTicks={150}
        warmupTicks={40}
        nodeRelSize={3}
        nodeVal={(n) => 1 + Math.sqrt((n as { degree: number }).degree)}
        nodeColor={(n) => ((n as { opted_in?: boolean }).opted_in === false ? '#606060' : (n as { isolated: boolean }).isolated ? '#fbbf24' : '#ededed')}
        nodeLabel={(n) => {
          const m = n as { name: string; degree: number; isolated: boolean; opted_in?: boolean; events?: { event_name: string }[] }
          const attendance = (m.events ?? []).map((event) => `<div style="color:#8c8c8c">Met at ${esc(event.event_name)}</div>`).join('')
          return `<div style="background:#0a0a0a;border:1px solid #292929;border-radius:8px;padding:4px 8px;font:12px Geist Sans,sans-serif;color:#ededed">${esc(m.name)}<span style="color:#8c8c8c;font-family:Geist Mono,monospace"> · ${m.opted_in === false ? 'not opted in' : m.isolated ? 'isolated' : `degree ${m.degree}`}</span>${attendance}</div>`
        }}
        linkColor={(l) => ((l as { kind: string }).kind === 'accept' ? 'rgba(74,222,128,.45)' : 'rgba(255,255,255,.12)')}
        linkWidth={(l) => ((l as { kind: string }).kind === 'accept' ? 1.2 : 0.5)}
        onNodeClick={(n) => { if ((n as { opted_in?: boolean }).opted_in !== false) onSelect?.((n as { id: number }).id) }}
      />
    </div>
  )
}
