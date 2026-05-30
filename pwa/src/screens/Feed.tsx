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
import { useFeedStore } from '../store/feed'
import { getFeed, postFeedback, postImpression, ApiError } from '../api'
import type { FeedArticle, FeedbackAction } from '../types/api'

const SWIPE_THRESHOLD = 100
const SWIPE_UP_THRESHOLD = 80
const SWIPE_DOWN_THRESHOLD = 80
const PULL_THRESHOLD = 80
const PAGE_SIZE = 20
// Start loading the next page when this many cards remain ahead of the user.
const PREFETCH_AHEAD = 5

// E7-S8 — empty-state threshold relaxation. The PWA doesn't know the server's
// SCORE_THRESHOLD, so the first step-down offer assumes 0.5 and decrements from
// there. State resets on full page reload.
const SCORE_STEP = 0.1
const INITIAL_OFFER_FLOOR = 0.4

function formatScore(value: number): string {
  return value <= 0 ? '0' : value.toFixed(1)
}

function EmptyDeck({
  currentFloor,
  onLower,
}: {
  currentFloor: number | null
  onLower: (next: number) => void
}) {
  // Next step-down offer: from the active floor when set, else from the
  // initial heuristic offer. Once the floor reaches 0, there's nothing more
  // to relax — show the resigned variant.
  const nextOffer =
    currentFloor === null
      ? INITIAL_OFFER_FLOOR
      : Math.max(currentFloor - SCORE_STEP, 0)
  const atZero = currentFloor !== null && currentFloor <= 0
  const showAllOffer = nextOffer === 0 && !atZero

  return (
    <div className="text-center" style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
      <p style={{ fontSize: 28, marginBottom: 8, color: 'var(--text-primary)' }}>
        Vous avez tout lu !
      </p>
      {atZero ? (
        <p>Revenez plus tard pour de nouveaux articles.</p>
      ) : (
        <>
          <p style={{ marginBottom: 16 }}>
            Pas envie d&apos;attendre ? Élargissez le filtre.
          </p>
          <button
            onClick={() => onLower(nextOffer)}
            style={{
              padding: '10px 16px',
              borderRadius: 20,
              border: '1px solid var(--accent-border)',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {showAllOffer
              ? 'Voir tous les articles (score ≥ 0)'
              : `Voir les articles avec score ≥ ${formatScore(nextOffer)}`}
          </button>
        </>
      )}
    </div>
  )
}

export const Feed = () => {
  // Snapshot from a prior mount (e.g. user navigated to /articles/:id and
  // tapped back). Hydrate state from it so the deck position is preserved.
  const snapshot = useFeedStore((s) => s.snapshot)
  const setSnapshot = useFeedStore((s) => s.setSnapshot)
  const clearSnapshot = useFeedStore((s) => s.clearSnapshot)
  // ArticleDetail signals via the store when a like/dislike/save was submitted
  // there, so the deck should advance past that article on return. Back button
  // does not raise the flag (Bonus on E7-S23).
  const consumeAdvance = useFeedStore((s) => s.consumeAdvance)

  const [articles, setArticles] = useState<FeedArticle[]>(
    () => snapshot?.articles ?? [],
  )
  const [cursor, setCursor] = useState<string | null>(
    () => snapshot?.cursor ?? null,
  )
  const [hasMore, setHasMore] = useState(() => snapshot?.hasMore ?? false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(
    () => (snapshot ? 'ready' : 'loading'),
  )
  const [errorMsg, setErrorMsg] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  // null = use server default. When the user opts into the relaxed empty
  // state, this becomes the active min_score override.
  const [minScore, setMinScore] = useState<number | null>(
    () => snapshot?.minScore ?? null,
  )
  const loadingMoreRef = useRef(false) // re-entrancy guard (not read during render)

  const [gone] = useState<Set<number>>(
    () => new Set<number>(snapshot?.goneIndices ?? []),
  )
  const [currentIndex, setCurrentIndex] = useState(
    () => snapshot?.currentIndex ?? 0,
  )
  const impressed = useRef<Set<string>>(
    new Set<string>(snapshot?.impressedIds ?? []),
  )
  const setFeedback = useFeedbackStore((s) => s.setFeedback)
  // True after the first mount has consumed any restored snapshot. Used to
  // skip the initial-load effect when we already restored data.
  const hadSnapshotOnMount = useRef(snapshot !== null)

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
    // Initial mount with a restored snapshot: skip the fetch — the deck is
    // already loaded. Subsequent reloadKey bumps clear this guard so refresh
    // and retry still re-fetch.
    if (hadSnapshotOnMount.current) {
      hadSnapshotOnMount.current = false
      return
    }
    let active = true
    getFeed(undefined, PAGE_SIZE, minScore ?? undefined)
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
  }, [reloadKey, gone, minScore])

  // Advance past an article when ArticleDetail signalled an action (Bonus on
  // E7-S23): consume the flag once on mount so a back-navigation that did not
  // raise it leaves the deck in place.
  useEffect(() => {
    if (status !== 'ready') return
    const advanceId = consumeAdvance()
    if (!advanceId) return
    const idx = articles.findIndex((a) => a.id === advanceId)
    if (idx === currentIndex && idx !== -1) {
      gone.add(idx)
      setCurrentIndex((prev) => Math.min(prev + 1, articles.length))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  // Persist the current state into the snapshot store. Runs on every change so
  // navigating away mid-deck (article detail) leaves a fresh snapshot behind.
  useEffect(() => {
    if (status !== 'ready') return
    setSnapshot({
      articles,
      cursor,
      hasMore,
      currentIndex,
      goneIndices: Array.from(gone),
      impressedIds: Array.from(impressed.current),
      minScore,
    })
  }, [
    status,
    articles,
    cursor,
    hasMore,
    currentIndex,
    gone,
    minScore,
    setSnapshot,
  ])

  const refresh = useCallback(() => {
    clearSnapshot()
    hadSnapshotOnMount.current = false
    setStatus('loading')
    setErrorMsg('')
    setReloadKey((k) => k + 1)
  }, [clearSnapshot])

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore || !cursor) return
    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const page = await getFeed(cursor, PAGE_SIZE, minScore ?? undefined)
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
  }, [cursor, hasMore, minScore])

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
      // Pass the full article so the Saved screen can show it immediately
      // (E7-S11). The store stashes it only when action === 'save'.
      setFeedback(article.id, action, article)
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
      <BlobBackground onRefresh={refresh} />

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

      {/* Active relaxed-threshold pill */}
      {minScore !== null && (
        <div
          className="relative z-10 flex justify-center"
          style={{ paddingTop: 'calc(env(safe-area-inset-top, 0px) + 12px)' }}
        >
          <button
            onClick={() => {
              clearSnapshot()
              hadSnapshotOnMount.current = false
              setStatus('loading')
              setMinScore(null)
            }}
            aria-label="Reset to default score threshold"
            style={{
              padding: '4px 10px',
              borderRadius: 20,
              border: '1px solid var(--accent-border)',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              fontSize: 11,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Score ≥ {formatScore(minScore)} · réinitialiser
          </button>
        </div>
      )}

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
            <EmptyDeck
              currentFloor={minScore}
              onLower={(next) => {
                clearSnapshot()
                hadSnapshotOnMount.current = false
                setStatus('loading')
                setMinScore(next)
              }}
            />
          )
        ) : (
          springs.map((props, i) => {
            // Only render the top card + the one immediately behind it. The
            // glass background is translucent on purpose, so stacking 3+ cards
            // makes text bleed through (E1-S2 regression).
            if (i < currentIndex || i > currentIndex + 1 || gone.has(i)) return null
            const isPeek = i === currentIndex + 1

            return (
              <animated.div
                key={articles[i].id}
                data-no-pull
                {...(isPeek ? {} : bind(i))}
                style={{
                  position: 'absolute',
                  width: '100%',
                  maxWidth: 360,
                  zIndex: articles.length - i,
                  // Peek sits slightly behind + scaled down. Pointer events off
                  // so the gesture binder only fires on the top card.
                  transform: isPeek
                    ? 'translate3d(0, 8px, 0) scale(0.96)'
                    : to(
                        [props.x, props.y, props.rot, props.scale],
                        (x, y, r, s) =>
                          `translate3d(${x}px,${y}px,0) rotate(${r}deg) scale(${s})`,
                      ),
                  opacity: isPeek ? 0.85 : props.opacity,
                  pointerEvents: isPeek ? 'none' : 'auto',
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
