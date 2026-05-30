import { useCallback, useEffect, useRef, useState } from 'react'

const TRAVEL_THRESHOLD = 80
const BOTTOM_THIRD_RATIO = 2 / 3

type RefreshState = {
  pulling: boolean
  refreshing: boolean
  progress: number
}

/**
 * Bottom-to-top drag on a background element triggers `onRefresh` (E7-S19).
 *
 * The touch must start in the bottom third of the viewport and travel at least
 * TRAVEL_THRESHOLD pixels upward before release. While dragging, `progress`
 * (0..1.5) is exposed so callers can animate a visual indicator. While the
 * refresh promise is in flight, `refreshing` stays true — a second gesture is
 * ignored until it resolves.
 */
export function usePullToRefresh(
  target: React.RefObject<HTMLElement | null>,
  onRefresh: (() => void | Promise<void>) | undefined,
): RefreshState {
  const [state, setState] = useState<RefreshState>({
    pulling: false,
    refreshing: false,
    progress: 0,
  })
  const startY = useRef<number | null>(null)
  const tracking = useRef(false)
  const refreshingRef = useRef(false)
  const progressRef = useRef(0)

  const finish = useCallback(() => {
    refreshingRef.current = false
    progressRef.current = 0
    setState({ pulling: false, refreshing: false, progress: 0 })
  }, [])

  useEffect(() => {
    const el = target.current
    if (!el || !onRefresh) return

    const onTouchStart = (e: TouchEvent) => {
      if (refreshingRef.current) return
      const touch = e.touches[0]
      if (!touch) return
      const vh = window.innerHeight
      if (touch.clientY < vh * BOTTOM_THIRD_RATIO) return
      startY.current = touch.clientY
      tracking.current = true
    }

    const onTouchMove = (e: TouchEvent) => {
      if (!tracking.current || startY.current === null) return
      const touch = e.touches[0]
      if (!touch) return
      const dy = startY.current - touch.clientY
      if (dy <= 0) {
        progressRef.current = 0
        setState((s) => (s.pulling ? { ...s, pulling: false, progress: 0 } : s))
        return
      }
      const progress = Math.min(dy / TRAVEL_THRESHOLD, 1.5)
      progressRef.current = progress
      setState({ pulling: true, refreshing: false, progress })
    }

    const onTouchEnd = () => {
      if (!tracking.current) return
      tracking.current = false
      startY.current = null
      if (progressRef.current >= 1 && !refreshingRef.current) {
        refreshingRef.current = true
        setState({ pulling: false, refreshing: true, progress: 1 })
        Promise.resolve(onRefresh()).finally(finish)
      } else {
        progressRef.current = 0
        setState({ pulling: false, refreshing: false, progress: 0 })
      }
    }

    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: true })
    el.addEventListener('touchend', onTouchEnd)
    el.addEventListener('touchcancel', onTouchEnd)
    return () => {
      el.removeEventListener('touchstart', onTouchStart)
      el.removeEventListener('touchmove', onTouchMove)
      el.removeEventListener('touchend', onTouchEnd)
      el.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [target, onRefresh, finish])

  return state
}
