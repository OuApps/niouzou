import { useState, useCallback, useRef, useEffect } from 'react'
import { useSprings, animated, to } from '@react-spring/web'
import { useDrag } from '@use-gesture/react'
import { ThumbsDown, Bookmark, ThumbsUp } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ArticleCard } from '../components/ArticleCard'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { useFeedbackStore } from '../store/feedback'
import { getFeed, postFeedback, postImpression, ApiError } from '../api'
import type { FeedArticle, FeedbackAction } from '../types/api'

const SWIPE_THRESHOLD = 100
const SWIPE_UP_THRESHOLD = 80
const SWIPE_DOWN_THRESHOLD = 80
const PULL_THRESHOLD = 80
const PAGE_SIZE = 20
// Start loading the next page when this many cards remain ahead of the user.
const PREFETCH_AHEAD = 5

export const Feed = () => {
  const [articles, setArticles] = useState<FeedArticle[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false) // re-entrancy guard (not read during render)

  const [gone] = useState(() => new Set<number>())
  const [currentIndex, setCurrentIndex] = useState(0)
  const impressed = useRef(new Set<string>())
  const setFeedback = useFeedbackStore((s) => s.setFeedback)

  // Pull-to-refresh state
  const [pullY, setPullY] = useState(0)
  const [pulling, setPulling] = useState(false)
  const touchStartY = useRef(0)
  const isPulling = useRef(false)

  const [springs, api] = useSprings(articles.length, () => ({
    x: 0,
    y: 0,
    scale: 1,
    rot: 0,
    opacity: 1,
  }))

  // ── Data loading ───────────────────────────────────────────────────────────

  // First page (and pull-to-refresh / retry re-fetches via reloadKey). State is
  // only set from the resolved promise, never synchronously in the effect body.
  useEffect(() => {
    let active = true
    getFeed(undefined, PAGE_SIZE)
      .then((page) => {
        if (!active) return
        gone.clear()
        impressed.current.clear()
        setArticles(page.articles)
        setCursor(page.next_cursor)
        setHasMore(page.has_more)
        setCurrentIndex(0)
        setStatus('ready')
      })
      .catch((e) => {
        if (!active) return
        setErrorMsg(e instanceof ApiError ? e.message : 'Could not load your feed.')
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [reloadKey, gone])

  const refresh = useCallback(() => {
    setStatus('loading')
    setErrorMsg('')
    setReloadKey((k) => k + 1)
  }, [])

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore || !cursor) return
    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const page = await getFeed(cursor, PAGE_SIZE)
      setArticles((prev) => [...prev, ...page.articles])
      setCursor(page.next_cursor)
      setHasMore(page.has_more)
    } catch {
      // Silent: the user can keep swiping what's loaded; a retry fires on the
      // next dismiss. Surfacing an inline error mid-deck would be jarring.
    } finally {
      loadingMoreRef.current = false
      setLoadingMore(false)
    }
  }, [cursor, hasMore])

  // Infinite scroll: prefetch as the user nears the end of the loaded deck.
  // Deferred a tick so the fetch's setState doesn't run synchronously here.
  useEffect(() => {
    if (status === 'ready' && hasMore && currentIndex >= articles.length - PREFETCH_AHEAD) {
      const t = setTimeout(loadMore, 0)
      return () => clearTimeout(t)
    }
  }, [currentIndex, articles.length, hasMore, status, loadMore])

  // Impression: record the top card as soon as it is displayed (once each).
  useEffect(() => {
    const top = articles[currentIndex]
    if (!top || impressed.current.has(top.id)) return
    impressed.current.add(top.id)
    postImpression(top.id).catch(() => {
      // Non-critical: a missed impression only risks re-showing later.
    })
  }, [articles, currentIndex])

  // ── Swiping ──────────────────────────────────────────────────────────────

  const dismiss = useCallback(
    (index: number, dir: 'left' | 'right' | 'up' | 'down') => {
      const article = articles[index]
      if (!article) return
      gone.add(index)

      // right=like, left=dislike, up=skip, down=save
      const action: FeedbackAction =
        dir === 'right' ? 'like' : dir === 'left' ? 'dislike' : dir === 'down' ? 'save' : 'skip'
      setFeedback(article.id, action)
      // Optimistic: the card is already flying off; persist in the background.
      postFeedback(article.id, action).catch(() => {})

      api.start((i) => {
        if (i !== index) return
        const x = dir === 'left' ? -500 : dir === 'right' ? 500 : 0
        const y = dir === 'up' ? -600 : dir === 'down' ? 600 : 0
        const rot = dir === 'left' ? -15 : dir === 'right' ? 15 : 0
        return {
          x,
          y,
          rot,
          scale: 0.8,
          opacity: 0,
          config: { friction: 30, tension: 200 },
        }
      })
      setCurrentIndex((prev) => Math.min(prev + 1, articles.length))
    },
    [api, articles, gone, setFeedback],
  )

  const bind = useDrag(
    ({ args: [index], active, movement: [mx, my], direction: [dx, dy], velocity: [vx, vy] }) => {
      const triggerRight = mx > SWIPE_THRESHOLD || (vx > 0.5 && dx > 0)
      const triggerLeft = mx < -SWIPE_THRESHOLD || (vx > 0.5 && dx < 0)
      const triggerUp = my < -SWIPE_UP_THRESHOLD || (vy > 0.5 && dy < 0)
      const triggerDown = my > SWIPE_DOWN_THRESHOLD || (vy > 0.5 && dy > 0)

      if (!active) {
        if (triggerRight) return dismiss(index, 'right')
        if (triggerLeft) return dismiss(index, 'left')
        if (triggerUp) return dismiss(index, 'up')
        if (triggerDown) return dismiss(index, 'down')

        api.start((i) => {
          if (i !== index) return
          return { x: 0, y: 0, rot: 0, scale: 1, opacity: 1 }
        })
        return
      }

      api.start((i) => {
        if (i !== index) return
        const rot = mx / 20
        return {
          x: mx,
          y: my,
          rot,
          scale: 1.02,
          opacity: 1,
          immediate: (key: string) => key === 'x' || key === 'y',
        }
      })
    },
    { filterTaps: true },
  )

  // ── Pull-to-refresh ────────────────────────────────────────────────────────
  // Derived here (before touch handlers) so handleTouchMove can close over it.
  const deckEmpty = currentIndex >= articles.length

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
    isPulling.current = false
  }, [])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    // When cards are present, swipe-down is the "save" gesture handled by the
    // card gesture recogniser — don't let it also trigger pull-to-refresh.
    if (status === 'ready' && !deckEmpty) return
    const dy = e.touches[0].clientY - touchStartY.current
    if (dy > 0 && window.scrollY === 0) {
      isPulling.current = true
      setPulling(true)
      setPullY(Math.min(dy * 0.5, 120))
    }
  }, [status, deckEmpty])

  const handleTouchEnd = useCallback(() => {
    if (isPulling.current && pullY > PULL_THRESHOLD) {
      refresh()
    }
    setPullY(0)
    setPulling(false)
    isPulling.current = false
  }, [pullY, refresh])

  const pullProgress = Math.min(pullY / PULL_THRESHOLD, 1)

  return (
    <div
      className="flex flex-col min-h-dvh relative"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      <BlobBackground />

      {/* Pull-to-refresh indicator */}
      <div
        className="pull-indicator"
        style={{
          transform: `translateY(${pullY - 40}px)`,
          opacity: pulling ? pullProgress : 0,
        }}
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            transform: `rotate(${pullProgress * 360}deg)`,
            transition: pulling ? 'none' : 'transform 0.3s ease',
          }}
        >
          <path d="M12 2v6" />
          <path d="m9 5 3-3 3 3" />
          <path d="M12 22v-6" />
          <path d="m15 19-3 3-3-3" />
        </svg>
      </div>

      {/* Card stack */}
      <div
        className="relative z-10 flex-1 flex items-center justify-center"
        style={{ padding: '0 20px', minHeight: 460 }}
      >
        {status === 'loading' ? (
          <Spinner size={32} />
        ) : status === 'error' ? (
          <ErrorState message={errorMsg} onRetry={refresh} />
        ) : deckEmpty ? (
          hasMore || loadingMore ? (
            <Spinner size={32} />
          ) : (
            <div className="text-center" style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              <p style={{ fontSize: 32, marginBottom: 12 }}>You are all caught up</p>
              <p>Check back later for new articles</p>
            </div>
          )
        ) : (
          springs.map((props, i) => {
            if (i < currentIndex || gone.has(i)) return null

            return (
              <animated.div
                key={articles[i].id}
                {...bind(i)}
                style={{
                  position: 'absolute',
                  width: '100%',
                  maxWidth: 360,
                  zIndex: articles.length - i,
                  transform: to(
                    [props.x, props.y, props.rot, props.scale],
                    (x, y, r, s) => `translate3d(${x}px,${y}px,0) rotate(${r}deg) scale(${s})`,
                  ),
                  opacity: props.opacity,
                  touchAction: 'none',
                }}
              >
                {/* Swipe tint overlays: right=cyan(like) left=red(dislike) down=yellow(save) */}
                <animated.div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    borderRadius: 28,
                    zIndex: 10,
                    pointerEvents: 'none',
                    background: to([props.x, props.y], (x, y) => {
                      if (x > 30) return `rgba(72, 202, 228, ${Math.min(Math.abs(x) / 300, 0.25)})`
                      if (x < -30) return `rgba(248, 113, 113, ${Math.min(Math.abs(x) / 300, 0.25)})`
                      if (y > 30) return `rgba(249, 199, 79, ${Math.min(Math.abs(y) / 300, 0.25)})`
                      return 'transparent'
                    }),
                  }}
                />
                <ArticleCard article={articles[i]} />
              </animated.div>
            )
          })
        )}
      </div>

      {/* Action buttons */}
      {status === 'ready' && !deckEmpty && (
        <div
          className="relative z-10 flex justify-center items-center gap-8"
          style={{ padding: '12px 0 24px' }}
        >
          <button
            onClick={() => dismiss(currentIndex, 'left')}
            aria-label="Dislike"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: 'var(--action-dislike)',
              fontSize: 26,
            }}
          >
            <ThumbsDown size={26} />
          </button>
          <button
            onClick={() => dismiss(currentIndex, 'down')}
            aria-label="Save"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: 'var(--action-save)',
              fontSize: 26,
            }}
          >
            <Bookmark size={26} />
          </button>
          <button
            onClick={() => dismiss(currentIndex, 'right')}
            aria-label="Like"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: 'var(--action-like)',
              fontSize: 26,
            }}
          >
            <ThumbsUp size={26} />
          </button>
        </div>
      )}

      <div style={{ height: 72 }} />
      <BottomNav />
    </div>
  )
}
