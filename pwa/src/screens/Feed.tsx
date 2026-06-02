import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { FeedArticleSlide } from '../components/FeedArticleSlide'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { diffForPost, useFeedbackStore } from '../store/feedback'
import { getFeed, postFeedback, postImpression, ApiError } from '../api'
import type { FeedArticle, FeedbackState, Reaction } from '../types/api'

const PAGE_SIZE = 20
// Prefetch the next page when this many slides remain ahead of the active one.
const PREFETCH_AHEAD = 5
// Impression threshold (E9-S2): slide must be ≥ 70% visible for ≥ 500 ms.
const IMPRESSION_VISIBILITY = 0.7
const IMPRESSION_DELAY_MS = 500

// E7-S8 — empty-state threshold relaxation (preserved from the swipe deck).
const SCORE_STEP = 0.1
const INITIAL_OFFER_FLOOR = 0.4

function formatScore(value: number): string {
  return value <= 0 ? '0' : value.toFixed(1)
}

export const Feed = () => {
  // E9-S3 — `?start=:id` pivots the first page on a specific article (taps
  // from Explore History / New and from Saved). We read the param once on
  // mount, then strip it from the URL so refreshes/scroll-snap reloads don't
  // keep re-applying the same pivot.
  const [searchParams, setSearchParams] = useSearchParams()
  const [startId, setStartId] = useState<string | null>(
    () => searchParams.get('start'),
  )
  useEffect(() => {
    if (searchParams.get('start') !== null) {
      const next = new URLSearchParams(searchParams)
      next.delete('start')
      setSearchParams(next, { replace: true })
    }
    // Run-once: we only want to clear the URL after the initial read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [articles, setArticles] = useState<FeedArticle[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  // null = use server default. Lowered via the empty-state CTA (E7-S8).
  const [minScore, setMinScore] = useState<number | null>(null)
  // Active slide index — updated by the IntersectionObserver. Drives prefetch.
  const [activeIndex, setActiveIndex] = useState(0)

  const loadingMoreRef = useRef(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const impressed = useRef<Set<string>>(new Set())
  const impressionTimers = useRef<Map<string, number>>(new Map())

  const applyFeedback = useFeedbackStore((s) => s.apply)
  const removeFeedback = useFeedbackStore((s) => s.remove)
  const getOverlay = useFeedbackStore((s) => s.get)

  // ── Data loading ───────────────────────────────────────────────────────────
  useEffect(() => {
    let active = true
    setStatus('loading')
    impressed.current.clear()
    impressionTimers.current.clear()
    getFeed({
      limit: PAGE_SIZE,
      minScore: minScore ?? undefined,
      start: startId ?? undefined,
    })
      .then((page) => {
        if (!active) return
        setArticles(page.articles)
        setCursor(page.next_cursor)
        setHasMore(page.has_more)
        setActiveIndex(0)
        setStatus('ready')
        // Pivot was already consumed on this fetch; drop it so the next reload
        // (refresh, threshold change) starts from a clean slate.
        if (startId !== null) setStartId(null)
        // The container resets to scrollTop=0 on remount, so this is mostly
        // a defensive call for subsequent reloads triggered from the empty
        // state buttons.
        requestAnimationFrame(() => {
          containerRef.current?.scrollTo({ top: 0, behavior: 'auto' })
        })
      })
      .catch((e) => {
        if (!active) return
        setErrorMsg(e instanceof ApiError ? e.message : 'Could not load your feed.')
        setStatus('error')
      })
    return () => {
      active = false
    }
    // startId only matters on the very first fetch (cleared above). Subsequent
    // reload triggers (`reloadKey` / `minScore`) don't depend on it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey, minScore])

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
      const page = await getFeed({
        cursor,
        limit: PAGE_SIZE,
        minScore: minScore ?? undefined,
      })
      setArticles((prev) => [...prev, ...page.articles])
      setCursor(page.next_cursor)
      setHasMore(page.has_more)
    } catch {
      // Silent: the user can keep reading what's loaded. A retry fires on the
      // next slide change.
    } finally {
      loadingMoreRef.current = false
      setLoadingMore(false)
    }
  }, [cursor, hasMore, minScore])

  // Infinite scroll — kick in N slides before the end of the loaded list.
  useEffect(() => {
    if (
      status === 'ready' &&
      hasMore &&
      activeIndex >= articles.length - PREFETCH_AHEAD
    ) {
      loadMore()
    }
  }, [activeIndex, articles.length, hasMore, status, loadMore])

  // E9-S2 — high-priority preload for the first two slides' hero images.
  // `loading="eager"` on the <img> already triggers a fetch, but a <link
  // rel="preload"> hoists the request to the browser's resource scheduler
  // before React mounts the image element, giving the user a faster LCP on
  // a cold deck. Cleaned up on every list change so subsequent pages don't
  // accumulate stale preload tags.
  useEffect(() => {
    if (status !== 'ready') return
    const urls = articles
      .slice(0, 2)
      .map((a) => a.og_image_url)
      .filter((u): u is string => Boolean(u))
    if (urls.length === 0) return
    const links = urls.map((href) => {
      const link = document.createElement('link')
      link.rel = 'preload'
      link.as = 'image'
      link.href = href
      document.head.appendChild(link)
      return link
    })
    return () => {
      for (const link of links) link.remove()
    }
  }, [articles, status])

  // ── Impression tracking ───────────────────────────────────────────────────
  const slideRefs = useRef<Map<string, HTMLElement>>(new Map())
  const observerRef = useRef<IntersectionObserver | null>(null)

  useEffect(() => {
    // Wire up a single observer for the lifetime of the screen; slides are
    // added/removed via `slideRefs`.
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.getAttribute('data-article-id')
          if (!id) continue
          if (entry.isIntersecting && entry.intersectionRatio >= IMPRESSION_VISIBILITY) {
            // Update active index whenever a slide is decisively visible.
            const index = articles.findIndex((a) => a.id === id)
            if (index !== -1) setActiveIndex(index)
            // Arm the impression timer — only fires if the slide stays put.
            if (impressed.current.has(id) || impressionTimers.current.has(id)) continue
            const timer = window.setTimeout(() => {
              impressionTimers.current.delete(id)
              if (impressed.current.has(id)) return
              impressed.current.add(id)
              postImpression(id).catch(() => {
                // Non-critical — the worst case is re-seeing the article.
              })
            }, IMPRESSION_DELAY_MS)
            impressionTimers.current.set(id, timer)
          } else {
            // User scrolled away before the timer fired — cancel it.
            const timer = impressionTimers.current.get(id)
            if (timer !== undefined) {
              window.clearTimeout(timer)
              impressionTimers.current.delete(id)
            }
          }
        }
      },
      {
        root: containerRef.current,
        threshold: [0, IMPRESSION_VISIBILITY, 1],
      },
    )
    observerRef.current = observer
    // Observe any slides that were already mounted (re-mount after reload).
    for (const node of slideRefs.current.values()) observer.observe(node)
    return () => {
      observer.disconnect()
      observerRef.current = null
      // Cancel any pending impression timer.
      for (const t of impressionTimers.current.values()) window.clearTimeout(t)
      impressionTimers.current.clear()
    }
    // Deliberately re-attach when the article list changes so the closure
    // captures the latest `articles` for the index lookup.
  }, [articles])

  const registerSlide = useCallback(
    (id: string) => (node: HTMLElement | null) => {
      const map = slideRefs.current
      const observer = observerRef.current
      const existing = map.get(id)
      if (existing && existing !== node) {
        observer?.unobserve(existing)
        map.delete(id)
      }
      if (node) {
        map.set(id, node)
        observer?.observe(node)
      }
    },
    [],
  )

  // ── Feedback ──────────────────────────────────────────────────────────────
  const send = useCallback(
    (article: FeedArticle, next: FeedbackState) => {
      const current = getOverlay(article.id, {
        reaction: article.reaction,
        is_saved: article.is_saved,
        read_full_article: article.read_full_article,
      })
      const diff = diffForPost(current, next)
      // No-op (nothing actually changed) — skip the round-trip.
      if (
        diff.reaction === undefined &&
        diff.is_saved === undefined &&
        diff.read_full_article === undefined
      ) {
        return
      }
      applyFeedback(article.id, next, article)
      postFeedback(article.id, diff).catch(() => {
        // Roll back optimistic state on failure — the user can re-tap.
        removeFeedback(article.id)
      })
    },
    [applyFeedback, getOverlay, removeFeedback],
  )

  const onReact = useCallback(
    (article: FeedArticle, reaction: Reaction) => {
      const current = getOverlay(article.id, {
        reaction: article.reaction,
        is_saved: article.is_saved,
        read_full_article: article.read_full_article,
      })
      send(article, { ...current, reaction })
    },
    [getOverlay, send],
  )

  const onToggleSave = useCallback(
    (article: FeedArticle) => {
      const current = getOverlay(article.id, {
        reaction: article.reaction,
        is_saved: article.is_saved,
        read_full_article: article.read_full_article,
      })
      send(article, { ...current, is_saved: !current.is_saved })
    },
    [getOverlay, send],
  )

  const onMarkRead = useCallback(
    (article: FeedArticle) => {
      const current = getOverlay(article.id, {
        reaction: article.reaction,
        is_saved: article.is_saved,
        read_full_article: article.read_full_article,
      })
      if (current.read_full_article) return
      send(article, { ...current, read_full_article: true })
    },
    [getOverlay, send],
  )

  // ── Render ────────────────────────────────────────────────────────────────
  if (status === 'loading') {
    return (
      <FullScreenShell>
        <Spinner size={32} />
        <BottomNav />
      </FullScreenShell>
    )
  }

  if (status === 'error') {
    return (
      <FullScreenShell>
        <ErrorState message={errorMsg} onRetry={refresh} />
        <BottomNav />
      </FullScreenShell>
    )
  }

  if (articles.length === 0) {
    return (
      <FullScreenShell>
        <EmptyDeck
          currentFloor={minScore}
          onLower={(next) => {
            setStatus('loading')
            setMinScore(next)
          }}
          onReset={
            minScore !== null
              ? () => {
                  setStatus('loading')
                  setMinScore(null)
                }
              : undefined
          }
        />
        <BottomNav />
      </FullScreenShell>
    )
  }

  return (
    <div className="relative" style={{ height: '100dvh' }}>
      <BlobBackground onRefresh={refresh} />

      {minScore !== null && (
        <button
          onClick={() => {
            setStatus('loading')
            setMinScore(null)
          }}
          aria-label="Reset to default score threshold"
          style={{
            position: 'absolute',
            top: 'calc(env(safe-area-inset-top, 0px) + 12px)',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 30,
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
          Score ≥ {formatScore(minScore)} · reset
        </button>
      )}

      <div ref={containerRef} className="feed-snap relative z-10" data-no-pull>
        {articles.map((article, index) => (
          <FeedArticleSlide
            key={article.id}
            article={article}
            imageEager={index < 2}
            slideRef={registerSlide(article.id)}
            onReact={(reaction) => onReact(article, reaction)}
            onToggleSave={() => onToggleSave(article)}
            onMarkRead={() => onMarkRead(article)}
          />
        ))}

        {loadingMore && (
          <div
            className="flex justify-center items-center"
            style={{ height: 80 }}
          >
            <Spinner size={22} />
          </div>
        )}
      </div>

      <BottomNav />
    </div>
  )
}

interface EmptyDeckProps {
  currentFloor: number | null
  onLower: (next: number) => void
  onReset?: () => void
}

const EmptyDeck = ({ currentFloor, onLower, onReset }: EmptyDeckProps) => {
  const nextOffer =
    currentFloor === null
      ? INITIAL_OFFER_FLOOR
      : Math.max(currentFloor - SCORE_STEP, 0)
  const atZero = currentFloor !== null && currentFloor <= 0
  const showAllOffer = nextOffer === 0 && !atZero

  return (
    <div className="text-center" style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
      <p style={{ fontSize: 28, marginBottom: 8, color: 'var(--text-primary)' }}>
        You&apos;re all caught up!
      </p>
      {atZero ? (
        <>
          <p style={{ marginBottom: 16 }}>
            Come back later for new articles.
          </p>
          {onReset && (
            <button
              onClick={onReset}
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
              Reset filter
            </button>
          )}
        </>
      ) : (
        <>
          <p style={{ marginBottom: 16 }}>
            Don&apos;t want to wait? Widen the filter.
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
              ? 'Show all articles (score ≥ 0)'
              : `Show articles with score ≥ ${formatScore(nextOffer)}`}
          </button>
        </>
      )}
    </div>
  )
}

const FullScreenShell = ({ children }: { children: React.ReactNode }) => (
  <div
    className="flex flex-col items-center justify-center relative"
    style={{ height: '100dvh' }}
  >
    <BlobBackground />
    <div className="relative z-10 flex flex-col items-center" style={{ padding: 20 }}>
      {children}
    </div>
  </div>
)
