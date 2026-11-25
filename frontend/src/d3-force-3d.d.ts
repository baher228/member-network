declare module 'd3-force-3d' {
  type Positional = { strength(s: number | ((n: unknown) => number)): Positional }
  export function forceX(x?: number): Positional
  export function forceY(y?: number): Positional
}
