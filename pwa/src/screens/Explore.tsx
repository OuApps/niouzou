import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ArticleListRow } from '../components/ArticleListRow'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { useInfiniteScroll } from '../hooks/useInfiniteScroll'
import {
  ApiError,
  getExploreHistory,
  getExploreNew,
  type ExploreHistoryArticle,
} from '../api'
import type { FeedArticle } from '../types/api'

const PAGE_SIZE = 20

type Mode = 'history' | 'new'

// Both endpoints return a `FeedArticle`; History adds `seen_at`. We carry the
// optional field on the row type so the component can render `seen_at` when
// available and `published_at` otherwise.
type Row = FeedArticle & { seen_at?: string }

interface TabState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  articles: Row[]
  cursor: string | null
  hasMore: boolean
  loadingMore: boolean
  errorMsg: string
}

const EMPTY: TabState = {
  status: 'idle',
  articles: [],
  cursor: null,
  hasMore: false,
  loadingMore: false,
  errorMsg: '',
}

const FETCHERS: Record<Mode, (cursor?: string, limit?: number) => Promise<{
  articles: (FeedArticle | ExploreHistoryArticle)[]
  next_cursor: string | null
  has_more: boolean
}>> = {
  history: getExploreHistory,
  new: getExploreNew,
}

export const Explore = () => {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('new')
  const [tabs, setTabs] = useState<Record<Mode, TabState>>({
    history: EMPTY,
    new: EMPTY,
  })
  const loadingMoreRef = useRef(false)

  const active = tabs[mode]

  const patch = useCallback((target: Mode, change: Partial<TabState>) => {
    setTabs((prev) => ({ ...prev, [target]: { ...prev[target], ...change } }))
  }, [])

  const fetchFirstPage = useCallback(
    async (target: Mode) => {
      patch(target, { status: 'loading' })
      try {
        const page = await FETCHERS[target](undefined, PAGE_SIZE)
        patch(target, {
          status: 'ready',
          articles: page.articles as Row[],
          cursor: page.next_cursor,
          hasMore: page.has_more,
          errorMsg: '',
        })
      } catch (e) {
        patch(target, {
          status: 'error',
          errorMsg:
            e instanceof ApiError ? e.message : 'Could not load Explore.',
        })
      }
    },
    [patch],
  )

  // Initial load of the active tab (and lazy-load on tab switch).
  useEffect(() => {
    if (active.status === 'idle') fetchFirstPage(mode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  const reload = useCallback(() => {
    // Drop both tabs so a tab switch after refresh always fetches fresh.
    setTabs({ history: EMPTY, new: EMPTY })
    fetchFirstPage(mode)
  }, [fetchFirstPage, mode])

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !active.hasMore || !active.cursor) return
    loadingMoreRef.current = true
    patch(mode, { loadingMore: true })
    try {
      const page = await FETCHERS[mode](active.cursor, PAGE_SIZE)
      setTabs((prev) => ({
        ...prev,
        [mode]: {
          ...prev[mode],
          articles: [...prev[mode].articles, ...(page.articles as Row[])],
          cursor: page.next_cursor,
          hasMore: page.has_more,
          loadingMore: false,
        },
      }))
    } catch {
      patch(mode, { loadingMore: false })
    } finally {
      loadingMoreRef.current = false
    }
  }, [active.cursor, active.hasMore, mode, patch])

  const sentinelRef = useInfiniteScroll({
    hasMore: active.hasMore,
    enabled: active.status === 'ready',
    onLoadMore: loadMore,
  })

  const openArticle = useCallback(
    (id: string) => {
      navigate(`/?start=${encodeURIComponent(id)}`)
    },
    [navigate],
  )

  return (
    <div className="flex flex-col h-dvh overflow-y-auto relative">
      <BlobBackground onRefresh={reload} />

      <header
        className="relative z-10 flex flex-col items-center"
        style={{
          padding: 'calc(env(safe-area-inset-top, 0px) + 12px) 20px 8px',
          gap: 12,
        }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Explore
        </h1>
        <Tabs mode={mode} onChange={setMode} />
      </header>

      <div className="relative z-10 flex-1" style={{ padding: '8px 16px 90px' }}>
        {active.status === 'loading' || active.status === 'idle' ? (
          <div className="flex justify-center" style={{ paddingTop: 60 }}>
            <Spinner size={30} />
          </div>
        ) : active.status === 'error' ? (
          <ErrorState message={active.errorMsg} onRetry={reload} />
        ) : active.articles.length === 0 ? (
          <EmptyState
            icon={Compass}
            title={mode === 'history' ? 'Aucun article lu' : 'Pas de nouveaux articles'}
            description={
              mode === 'history'
                ? 'Reviens ici après avoir parcouru ton feed pour retrouver les articles déjà vus.'
                : 'Reviens plus tard — le prochain enrichissement va apporter de nouveaux articles.'
            }
          />
        ) : (
          <div className="flex flex-col gap-3">
            {active.articles.map((article) => (
              <ArticleListRow
                key={article.id}
                article={article}
                timestamp={
                  mode === 'history' && article.seen_at
                    ? article.seen_at
                    : article.published_at
                }
                onClick={() => openArticle(article.id)}
                // History reflects per-article state; New is always default,
                // so we hide the icon row to keep the visual lighter.
                showState={mode === 'history'}
              />
            ))}
            {active.hasMore && (
              <div
                ref={sentinelRef}
                className="flex justify-center"
                style={{ padding: '8px 0 24px' }}
              >
                {active.loadingMore && <Spinner size={22} />}
              </div>
            )}
          </div>
        )}
      </div>

      <BottomNav />
    </div>
  )
}

const Tabs = ({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) => (
  <div
    className="flex"
    style={{
      gap: 4,
      padding: 4,
      borderRadius: 24,
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.08)',
    }}
  >
    {(['new', 'history'] as Mode[]).map((m) => {
      const isActive = m === mode
      return (
        <button
          key={m}
          onClick={() => onChange(m)}
          style={{
            padding: '6px 18px',
            borderRadius: 20,
            border: 'none',
            cursor: 'pointer',
            fontSize: 12,
            fontWeight: 600,
            color: isActive ? 'var(--accent)' : 'var(--text-tertiary)',
            background: isActive ? 'var(--accent-subtle)' : 'transparent',
          }}
        >
          {m === 'history' ? 'Lus' : 'Nouveaux'}
        </button>
      )
    })}
  </div>
)
