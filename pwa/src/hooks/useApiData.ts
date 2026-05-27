import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/http'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Run an async API call on mount, exposing loading / error / data plus a
 * `reload`. Errors are reduced to a friendly message (never raw JSON), per
 * E4-S3. `deps` re-runs the fetcher when they change.
 *
 * State is only ever set from the resolved promise (or the reload handler),
 * never synchronously inside the effect body.
 */
export function useApiData<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    fetcher()
      .then((d) => {
        if (!active) return
        setData(d)
        setError(null)
      })
      .catch((e) => {
        if (!active) return
        setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
    // fetcher identity changes every render by design; gate on caller deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadKey])

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    setReloadKey((k) => k + 1)
  }, [])

  return { data, loading, error, reload }
}
