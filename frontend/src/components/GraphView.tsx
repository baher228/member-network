import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import type { GraphResponse } from '../api'

export default function GraphView({ graph, onSelect }: { graph: GraphResponse; onSelect?: (id: number) => void }) {
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800)
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const data = useMemo(() => ({
    nodes: graph.nodes.map((n) => ({ ...n })),
    links: graph.edges.map((e) => ({ ...e })),
  }), [graph])
  return (
    <div ref={wrap} className="w-full overflow-hidden rounded-xl border border-line bg-card">
      <ForceGraph2D
        graphData={data}
        width={width}
        height={width < 500 ? 320 : 420}
        backgroundColor="#121212"
        cooldownTicks={120}
        nodeRelSize={3}
        nodeVal={(n) => 1 + Math.sqrt((n as { degree: number }).degree)}
        nodeColor={(n) => ((n as { isolated: boolean }).isolated ? '#fbbf24' : '#ededed')}
        nodeLabel={(n) => `${(n as { name: string }).name} · degree ${(n as { degree: number }).degree}`}
        linkColor={(l) => ((l as { kind: string }).kind === 'accept' ? 'rgba(74,222,128,.45)' : 'rgba(255,255,255,.12)')}
        linkWidth={(l) => ((l as { kind: string }).kind === 'accept' ? 1.2 : 0.5)}
        onNodeClick={(n) => onSelect?.((n as { id: number }).id)}
      />
    </div>
  )
}
