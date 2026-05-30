import { useCallback, useEffect, useRef, useState } from 'react'

const TRAVEL_THRESHOLD = 80
const BOTTOM_THIRD_RATIO = 2 / 3
// Touches that start on any of these never trigger the gesture — cards,
// buttons, links, form controls, and explicit opt-outs.
const EXCLUDE_SELECTOR =
  'button, a, input, textarea, select, [role="button"], [data-no-pull], .article-card'

type RefreshState = {
  pulling: boolean
  refreshing: boolean
  progress: number
}

/**
 * Bottom-to-top drag triggers `onRefresh` (E7-S19).
 *
 * Listeners attach at the window level (not on a ref) because `BlobBackground`
 * is `position: fixed; inset: 0` but sits behind the screen content — touches
 * almost never land on it directly. So we listen everywhere and filter:
 *
 *   - touchstart Y must be in the bottom third of the viewport
 *   - touch target must not be inside an interactive element (button, link,
 *     card, form control) — see EXCLUDE_SELECTOR
 *   - touch must travel upward by TRAVEL_THRESHOLD pixels before release
 *
 * `progress` (0..1.5) lets the caller animate a visual indicator; `refreshing`
 * stays true while the returned promise is in flight so a second gesture is
 * ignored.
 */
export function usePullToRefresh(
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
    if (!onRefresh) return

    const isPullable = (target: EventTarget | null): boolean => {
      if (!(target instanceof Element)) return true
      return target.closest(EXCLUDE_SELECTOR) === null
    }

    const onTouchStart = (e: TouchEvent) => {
      if (refreshingRef.current) return
      const touch = e.touches[0]
      if (!touch) return
      if (touch.clientY < window.innerHeight * BOTTOM_THIRD_RATIO) return
      if (!isPullable(e.target)) return
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

    // Mirror touch events as pointer events so dev testing on desktop (mouse)
    // also works. Filtered to primary-button drags only.
    let mouseDown = false
    const onPointerDown = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return
      if (e.button !== 0) return
      mouseDown = true
      if (refreshingRef.current) return
      if (e.clientY < window.innerHeight * BOTTOM_THIRD_RATIO) return
      if (!isPullable(e.target)) return
      startY.current = e.clientY
      tracking.current = true
    }
    const onPointerMove = (e: PointerEvent) => {
      if (e.pointerType === 'touch' || !mouseDown) return
      if (!tracking.current || startY.current === null) return
      const dy = startY.current - e.clientY
      if (dy <= 0) {
        progressRef.current = 0
        setState((s) => (s.pulling ? { ...s, pulling: false, progress: 0 } : s))
        return
      }
      const progress = Math.min(dy / TRAVEL_THRESHOLD, 1.5)
      progressRef.current = progress
      setState({ pulling: true, refreshing: false, progress })
    }
    const onPointerUp = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return
      mouseDown = false
      onTouchEnd()
    }

    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchmove', onTouchMove, { passive: true })
    window.addEventListener('touchend', onTouchEnd)
    window.addEventListener('touchcancel', onTouchEnd)
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    return () => {
      window.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('touchend', onTouchEnd)
      window.removeEventListener('touchcancel', onTouchEnd)
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
    }
  }, [onRefresh, finish])

  return state
}
