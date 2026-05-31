import { useEffect, useRef } from 'react'

interface Options {
  /** False when there's no next page; the observer disconnects. */
  hasMore: boolean
  /** Pause the observer until the screen is ready (e.g. initial fetch done). */
  enabled?: boolean
  /** Called when the sentinel scrolls into view. Idempotency is the caller's job. */
  onLoadMore: () => void
  /** Distance ahead of the sentinel at which the load fires. Default `200px`. */
  rootMargin?: string
}

/**
 * Mounts an IntersectionObserver on a sentinel element and calls `onLoadMore`
 * when it enters the viewport. Returns a ref to attach to the sentinel `<div>`.
 *
 * Shared by Saved + Explore History/New (E9 review refactor). Each callsite
 * still owns its in-flight guard since the right behaviour on a double-fire
 * is screen-specific (e.g. the Feed prefetches differently).
 */
export function useInfiniteScroll({
  hasMore,
  enabled = true,
  onLoadMore,
  rootMargin = '200px',
}: Options) {
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !hasMore || !enabled) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) onLoadMore()
      },
      { rootMargin },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasMore, enabled, onLoadMore, rootMargin])
  return sentinelRef
}
