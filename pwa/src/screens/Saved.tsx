import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bookmark } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ScoreBadge } from '../components/ScoreBadge'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { useFeedbackStore } from '../store/feedback'
import { useFeedStore } from '../store/feed'
import { getSaved, ApiError } from '../api'
import type { SavedArticle } from '../types/api'

const PAGE_SIZE = 20

export const Saved = () => {
  const navigate = useNavigate()
  // Snapshot from a prior mount (e.g. came back from /articles/:id). When
  // present, rehydrate state and skip the initial fetch so scroll + loaded
  // pages are preserved (E7-S23).
  const savedSnapshot = useFeedStore((s) => s.savedSnapshot)
  const setSavedSnapshot = useFeedStore((s) => s.setSavedSnapshot)
  const clearSavedSnapshot = useFeedStore((s) => s.clearSavedSnapshot)

  const [articles, setArticles] = useState<SavedArticle[]>(
    () => savedSnapshot?.articles ?? [],
  )
  const [cursor, setCursor] = useState<string | null>(
    () => savedSnapshot?.cursor ?? null,
  )
  const [hasMore, setHasMore] = useState(() => savedSnapshot?.hasMore ?? false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(
    () => (savedSnapshot ? 'ready' : 'loading'),
  )
  const [errorMsg, setErrorMsg] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)
  const hadSnapshotOnMount = useRef(savedSnapshot !== null)
  const restoredScrollY = useRef(savedSnapshot?.scrollY ?? 0)
  // Outer wrapper owns the scroll (h-dvh + overflow-y-auto), so snapshot
  // save/restore reads scrollTop from this ref — `window.scrollY` would
  // always be 0 here (E7-S29).
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)

  // Session overlay: hide unsaved rows, prepend optimistically-saved articles.
  const feedbacks = useFeedbackStore((s) => s.feedbacks)
  const sessionSaved = useFeedbackStore((s) => s.savedArticles)

  // ── Initial load + reload ──────────────────────────────────────────────────
  useEffect(() => {
    if (hadSnapshotOnMount.current) {
      hadSnapshotOnMount.current = false
      // Restore scroll on the next paint, once the rendered rows occupy
      // enough height for the scroll position to be reachable.
      requestAnimationFrame(() => {
        scrollContainerRef.current?.scrollTo({ top: restoredScrollY.current })
      })
      return
    }
    let active = true
    setStatus('loading')
    getSaved(undefined, PAGE_SIZE)
      .then((page) => {
        if (!active) return
        setArticles(page.articles)
        setCursor(page.next_cursor)
        setHasMore(page.has_more)
        setStatus('ready')
      })
      .catch((e) => {
        if (!active) return
        setErrorMsg(e instanceof ApiError ? e.message : 'Something went wrong.')
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  const reload = useCallback(() => {
    clearSavedSnapshot()
    hadSnapshotOnMount.current = false
    setReloadKey((k) => k + 1)
  }, [clearSavedSnapshot])

  // Persist a snapshot of the loaded list so navigating to an article detail
  // and back doesn't lose the user's place. Scroll position is captured at
  // the moment of navigation by the row's onClick (see below).
  useEffect(() => {
    if (status !== 'ready') return
    setSavedSnapshot({
      articles,
      cursor,
      hasMore,
      scrollY: 0,
    })
  }, [status, articles, cursor, hasMore, setSavedSnapshot])

  const openArticle = useCallback(
    (id: string) => {
      // Capture scroll at the click moment — the unmount can race a state
      // update so we write it directly into the store.
      setSavedSnapshot({
        articles,
        cursor,
        hasMore,
        scrollY: scrollContainerRef.current?.scrollTop ?? 0,
      })
      navigate(`/articles/${id}`)
    },
    [articles, cursor, hasMore, navigate, setSavedSnapshot],
  )

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore || !cursor) return
    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const page = await getSaved(cursor, PAGE_SIZE)
      setArticles((prev) => [...prev, ...page.articles])
      setCursor(page.next_cursor)
      setHasMore(page.has_more)
    } catch {
      // Silent: user can keep scrolling what's loaded.
    } finally {
      loadingMoreRef.current = false
      setLoadingMore(false)
    }
  }, [cursor, hasMore])

  // ── Infinite scroll: load next page when sentinel is in view ──────────────
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !hasMore || status !== 'ready') return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore()
      },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasMore, status, loadMore])

  // ── Merge session overlay over server response ────────────────────────────
  // Hide rows the user unsaved this session, and prepend session-saved articles
  // not yet present in the server page (E7-S11).
  const serverIds = new Set(articles.map((a) => a.id))
  const sessionExtras = Object.values(sessionSaved)
    .filter((a) => !serverIds.has(a.id))
    .sort((a, b) => b.saved_at.localeCompare(a.saved_at))
  const visibleArticles = [...sessionExtras, ...articles].filter(
    (a) => !(a.id in feedbacks) || feedbacks[a.id] === 'save',
  )

  return (
    <div
      ref={scrollContainerRef}
      className="flex flex-col h-dvh overflow-y-auto relative"
    >
      <BlobBackground onRefresh={reload} />

      <header
        className="relative z-10 flex items-center justify-center"
        style={{ padding: '16px 20px 8px' }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Saved
        </h1>
      </header>

      <div className="relative z-10 flex-1" style={{ padding: '8px 16px 90px' }}>
        {status === 'loading' ? (
          <div className="flex justify-center" style={{ paddingTop: 60 }}>
            <Spinner size={30} />
          </div>
        ) : status === 'error' ? (
          <ErrorState message={errorMsg} onRetry={reload} />
        ) : visibleArticles.length === 0 ? (
          <EmptyState
            icon={Bookmark}
            title="No saved articles"
            description="Articles you save will appear here. Swipe up or tap the bookmark icon to save."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {visibleArticles.map((article) => (
              <button
                key={article.id}
                onClick={() => openArticle(article.id)}
                className="glass-sm flex items-start gap-3 w-full text-left"
                style={{
                  borderRadius: 16,
                  padding: 12,
                  cursor: 'pointer',
                  border: '1px solid rgba(255,255,255,0.10)',
                  background: 'var(--glass-bg)',
                }}
              >
                {article.og_image_url && (
                  <img
                    src={article.og_image_url}
                    alt=""
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: 10,
                      objectFit: 'cover',
                      flexShrink: 0,
                    }}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div
                    className="flex items-center gap-2"
                    style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4 }}
                  >
                    <span
                      title={article.source.name}
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        minWidth: 0,
                        flexShrink: 1,
                      }}
                    >
                      {article.source.name}
                    </span>
                    <span style={{ flexShrink: 0 }}>
                      <ScoreBadge score={article.relevance_score} scorer={article.scorer} />
                    </span>
                  </div>
                  <h3
                    title={article.title}
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      lineHeight: 1.35,
                      margin: '0 0 4px',
                      color: 'var(--text-primary)',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      wordBreak: 'break-word',
                    }}
                  >
                    {article.title}
                  </h3>
                  <p style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                    {formatTimeAgo(article.published_at)}
                  </p>
                </div>
              </button>
            ))}
            {/* Infinite scroll sentinel */}
            {hasMore && (
              <div
                ref={sentinelRef}
                className="flex justify-center"
                style={{ padding: '8px 0 24px' }}
              >
                {loadingMore && <Spinner size={22} />}
              </div>
            )}
          </div>
        )}
      </div>

      <BottomNav />
    </div>
  )
}
