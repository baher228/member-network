import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react'

const cache = new Map<string, unknown>()

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const key = fn.toString() + JSON.stringify(deps)
  const keyRef = useRef(key)
  keyRef.current = key
  const [data, setDataState] = useState<T | null>(() => (cache.get(key) as T | undefined) ?? null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(() => !cache.has(key))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)
  const setData = useCallback((value: SetStateAction<T | null>) => {
    setDataState((prev) => {
      const next = typeof value === 'function' ? (value as (p: T | null) => T | null)(prev) : value
      cache.set(keyRef.current, next)
      return next
    })
  }, [])
  const reload = useCallback(async () => {
    const k = keyRef.current
    if (cache.has(k)) setDataState(cache.get(k) as T)
    else { setDataState(null); setLoading(true) }
    setError(null)
    try {
      const result = await run()
      cache.set(k, result)
      if (keyRef.current === k) setDataState(result)
    } catch (e) {
      if (keyRef.current === k) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (keyRef.current === k) setLoading(false)
    }
  }, [run])
  useEffect(() => { void reload() }, [reload])
  return { data, error, loading, reload, setData }
}
