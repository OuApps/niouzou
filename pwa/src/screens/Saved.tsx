import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bookmark } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ArticleListRow } from '../components/ArticleListRow'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { useInfiniteScroll } from '../hooks/useInfiniteScroll'
import { useFeedbackStore } from '../store/feedback'
import { getSaved, ApiError } from '../api'
import type { SavedArticle } from '../types/api'

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

  // Session overlay (E9-S1/S2): mirror the user's local feedback so unsaved
  // rows disappear and freshly-saved rows show up before the next refresh.
  const overrides = useFeedbackStore((s) => s.overrides)
  const sessionSaved = useFeedbackStore((s) => s.savedArticles)

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
      // backend honours ?start= via E9-S3.
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

  const sentinelRef = useInfiniteScroll({
    hasMore,
    enabled: status === 'ready',
    onLoadMore: loadMore,
  })

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
    <div className="flex flex-col h-dvh overflow-y-auto relative">
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
            {visibleArticles.map((article) => (
              <ArticleListRow
                key={article.id}
                article={article}
                timestamp={article.published_at}
                onClick={() => openArticle(article.id)}
                showState
                forceSaved
              />
            ))}
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
