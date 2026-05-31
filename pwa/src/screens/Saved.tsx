import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bookmark,
  ThumbsUp,
  ThumbsDown,
  BookOpen,
} from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ScoreBadge } from '../components/ScoreBadge'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { useFeedbackStore } from '../store/feedback'
import { getSaved, ApiError } from '../api'
import type { FeedbackState, SavedArticle } from '../types/api'

const PAGE_SIZE = 20

export const Saved = () => {
  const navigate = useNavigate()

  const [articles, setArticles] = useState<SavedArticle[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)
  // Outer wrapper owns the scroll (h-dvh + overflow-y-auto). Scroll position
  // is no longer restored across navigation now that ArticleDetail is gone —
  // Saved → Feed is a top-level transition that fully remounts (E9-S4).
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)

  // Session overlay (E9-S1/S2): mirror the user's local feedback so unsaved
  // rows disappear and freshly-saved rows show up before the next refresh.
  const overrides = useFeedbackStore((s) => s.overrides)
  const sessionSaved = useFeedbackStore((s) => s.savedArticles)
  const getOverlay = useFeedbackStore((s) => s.get)

  // ── Initial load + reload ──────────────────────────────────────────────────
  useEffect(() => {
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
    setReloadKey((k) => k + 1)
  }, [])

  const openArticle = useCallback(
    (id: string) => {
      // E9-S4: navigate into the Feed with the article as the pivot. The
      // backend `?start=` handling lands with E9-S3 — until then the user is
      // dropped on the regular feed (acceptable transitional state).
      navigate(`/?start=${encodeURIComponent(id)}`)
    },
    [navigate],
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
  // 1. Hide rows the user un-saved this session.
  // 2. Prepend articles saved this session that the server hasn't returned yet.
  const serverIds = new Set(articles.map((a) => a.id))
  const sessionExtras = Object.values(sessionSaved)
    .filter((a) => !serverIds.has(a.id))
    .sort((a, b) => b.saved_at.localeCompare(a.saved_at))
  const visibleArticles = [...sessionExtras, ...articles].filter((a) => {
    const override = overrides[a.id]
    if (!override) return true
    return override.is_saved
  })

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
            description="Articles you save will appear here. Tap the bookmark icon on a feed slide to save."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {visibleArticles.map((article) => {
              const state: FeedbackState = getOverlay(article.id, {
                reaction: article.reaction,
                is_saved: article.is_saved,
                read_full_article: article.read_full_article,
              })
              return (
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
                        margin: '0 0 6px',
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
                    <StateIcons state={state} />
                    <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 4 }}>
                      {formatTimeAgo(article.published_at)}
                    </p>
                  </div>
                </button>
              )
            })}
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

const StateIcons = ({ state }: { state: FeedbackState }) => (
  <div className="flex items-center" style={{ gap: 10 }}>
    <Bookmark
      size={13}
      // Bookmark is the implicit definition of being in this list — always
      // active. Kept here for visual parity with Explore History rows.
      style={{
        color: 'var(--action-save)',
        fill: 'var(--action-save)',
      }}
    />
    <ThumbsUp
      size={13}
      style={{
        color:
          state.reaction === 'like'
            ? 'var(--action-like)'
            : 'var(--text-tertiary)',
        fill: state.reaction === 'like' ? 'var(--action-like)' : 'none',
      }}
    />
    <ThumbsDown
      size={13}
      style={{
        color:
          state.reaction === 'dislike'
            ? 'var(--action-dislike)'
            : 'var(--text-tertiary)',
        fill:
          state.reaction === 'dislike'
            ? 'var(--action-dislike)'
            : 'none',
      }}
    />
    <BookOpen
      size={13}
      style={{
        color: state.read_full_article
          ? 'var(--text-secondary)'
          : 'var(--text-tertiary)',
        opacity: state.read_full_article ? 1 : 0.5,
      }}
    />
  </div>
)
