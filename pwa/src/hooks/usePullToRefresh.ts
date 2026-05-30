import { useCallback, useEffect, useRef, useState } from 'react'

const TRAVEL_THRESHOLD = 80
const TOP_THIRD_RATIO = 1 / 3
const EXCLUDE_SELECTOR =
  'button, a, input, textarea, select, [role="button"], [data-no-pull], .article-card'

type RefreshState = {
  pulling: boolean
  refreshing: boolean
  progress: number
}

/**
 * Walk up the DOM from `start` and return the first ancestor whose `overflow-y`
 * makes it scrollable (`auto` or `scroll`). Falls back to `null` when no such
 * ancestor exists — caller then treats the document/window as the scroller.
 */
function findScrollableAncestor(start: Element): Element | null {
  let el: Element | null = start
  while (el && el !== document.body && el !== document.documentElement) {
    const style = window.getComputedStyle(el)
    const overflowY = style.overflowY
    if ((overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
      return el
    }
    el = el.parentElement
  }
  return null
}

/**
 * Classic top-to-bottom pull-to-refresh (E7-S19).
 *
 * Listens at the window level and filters:
 *   - touchstart Y must be in the top third of the viewport
 *   - touch target must not be inside an interactive element (button, link,
 *     card, form control) — see EXCLUDE_SELECTOR
 *   - the nearest scrollable ancestor (or the window) must already be at the
 *     top — otherwise the user is scrolling the content, not refreshing
 *   - touch must travel downward by TRAVEL_THRESHOLD pixels before release
 *
 * Once armed, touchmove calls `preventDefault()` so the browser doesn't pick
 * up the gesture as a native scroll and steal the rest of it (this was the
 * reason the gesture only "worked" on screens whose content fit in the
 * viewport). That requires the move listener to be non-passive.
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

    const atTop = (target: EventTarget | null): boolean => {
      if (!(target instanceof Element)) return window.scrollY === 0
      const scroller = findScrollableAncestor(target)
      if (scroller) return scroller.scrollTop === 0
      return window.scrollY === 0
    }

    const armFromStart = (clientY: number, target: EventTarget | null) => {
      if (refreshingRef.current) return
      if (clientY > window.innerHeight * TOP_THIRD_RATIO) return
      if (!isPullable(target)) return
      if (!atTop(target)) return
      startY.current = clientY
      tracking.current = true
    }

    const updateFromMove = (clientY: number) => {
      if (!tracking.current || startY.current === null) return
      const dy = clientY - startY.current
      if (dy <= 0) {
        progressRef.current = 0
        setState((s) => (s.pulling ? { ...s, pulling: false, progress: 0 } : s))
        return
      }
      const progress = Math.min(dy / TRAVEL_THRESHOLD, 1.5)
      progressRef.current = progress
      setState({ pulling: true, refreshing: false, progress })
    }

    const release = () => {
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

    const onTouchStart = (e: TouchEvent) => {
      const t = e.touches[0]
      if (t) armFromStart(t.clientY, e.target)
    }
    const onTouchMove = (e: TouchEvent) => {
      const t = e.touches[0]
      if (!t) return
      if (tracking.current && startY.current !== null && t.clientY > startY.current) {
        // Suppress native scroll so the browser doesn't hijack the gesture
        // mid-pull. Safe to call because we already verified atTop() at start.
        if (e.cancelable) e.preventDefault()
      }
      updateFromMove(t.clientY)
    }

    // Mirror touch as pointer events so devtools desktop testing (mouse) works.
    let mouseDown = false
    const onPointerDown = (e: PointerEvent) => {
      if (e.pointerType === 'touch' || e.button !== 0) return
      mouseDown = true
      armFromStart(e.clientY, e.target)
    }
    const onPointerMove = (e: PointerEvent) => {
      if (e.pointerType === 'touch' || !mouseDown) return
      updateFromMove(e.clientY)
    }
    const onPointerUp = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return
      mouseDown = false
      release()
    }

    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchmove', onTouchMove, { passive: false })
    window.addEventListener('touchend', release)
    window.addEventListener('touchcancel', release)
    window.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    return () => {
      window.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('touchend', release)
      window.removeEventListener('touchcancel', release)
      window.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
    }
  }, [onRefresh, finish])

  return state
}
