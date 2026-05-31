import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Compass,
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
import {
  ApiError,
  getExploreHistory,
  getExploreNew,
  type ExploreHistoryArticle,
} from '../api'
import type { FeedArticle, FeedbackState } from '../types/api'

const PAGE_SIZE = 20

type Mode = 'history' | 'new'

// Internal shape the rows accept — History adds `seen_at`, New uses `published_at`.
type Row = FeedArticle & { seen_at?: string }

export const Explore = () => {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('history')
  const [historyState, setHistoryState] = useState(emptyTabState<ExploreHistoryArticle>())
  const [newState, setNewState] = useState(emptyTabState<FeedArticle>())

  const activeState = mode === 'history' ? historyState : newState
  const setActiveState =
    mode === 'history'
      ? (setHistoryState as React.Dispatch<React.SetStateAction<TabState<Row>>>)
      : (setNewState as React.Dispatch<React.SetStateAction<TabState<Row>>>)

  const loadingMoreRef = useRef(false)

  const overrides = useFeedbackStore((s) => s.overrides)
  const getOverlay = useFeedbackStore((s) => s.get)

  const fetchFirstPage = useCallback(async (target: Mode) => {
    const fetcher = target === 'history' ? getExploreHistory : getExploreNew
    setActiveStateFor(target, { status: 'loading' })
    try {
      const page = await fetcher(undefined, PAGE_SIZE)
      setActiveStateFor(target, {
        status: 'ready',
        articles: page.articles as Row[],
        cursor: page.next_cursor,
        hasMore: page.has_more,
        errorMsg: '',
      })
    } catch (e) {
      setActiveStateFor(target, {
        status: 'error',
        errorMsg:
          e instanceof ApiError ? e.message : 'Could not load Explore.',
      })
    }
    function setActiveStateFor(t: Mode, patch: Partial<TabState<Row>>) {
      if (t === 'history')
        setHistoryState((s) => ({ ...(s as TabState<Row>), ...patch }) as TabState<ExploreHistoryArticle>)
      else setNewState((s) => ({ ...s, ...patch }) as TabState<FeedArticle>)
    }
  }, [])

  // Initial load of the active tab, plus reload when the user switches tabs to
  // one that hasn't been loaded yet.
  useEffect(() => {
    if (activeState.status === 'idle') fetchFirstPage(mode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  const reload = useCallback(() => {
    // Drop both tabs so when the user switches back the data is fresh — keeps
    // the overlay logic simple at the cost of an extra request on tab switch.
    setHistoryState(emptyTabState())
    setNewState(emptyTabState())
    fetchFirstPage(mode)
  }, [fetchFirstPage, mode])

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !activeState.hasMore || !activeState.cursor) return
    loadingMoreRef.current = true
    setActiveState((s) => ({ ...s, loadingMore: true }))
    try {
      const fetcher = mode === 'history' ? getExploreHistory : getExploreNew
      const page = await fetcher(activeState.cursor, PAGE_SIZE)
      setActiveState((s) => ({
        ...s,
        articles: [...s.articles, ...(page.articles as Row[])],
        cursor: page.next_cursor,
        hasMore: page.has_more,
        loadingMore: false,
      }))
    } catch {
      setActiveState((s) => ({ ...s, loadingMore: false }))
    } finally {
      loadingMoreRef.current = false
    }
  }, [activeState.cursor, activeState.hasMore, mode, setActiveState])

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !activeState.hasMore || activeState.status !== 'ready') return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore()
      },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [activeState.hasMore, activeState.status, loadMore])

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
          padding:
            'calc(env(safe-area-inset-top, 0px) + 12px) 20px 8px',
          gap: 12,
        }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Explore
        </h1>
        <Tabs mode={mode} onChange={setMode} />
      </header>

      <div className="relative z-10 flex-1" style={{ padding: '8px 16px 90px' }}>
        {activeState.status === 'loading' || activeState.status === 'idle' ? (
          <div className="flex justify-center" style={{ paddingTop: 60 }}>
            <Spinner size={30} />
          </div>
        ) : activeState.status === 'error' ? (
          <ErrorState message={activeState.errorMsg} onRetry={reload} />
        ) : activeState.articles.length === 0 ? (
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
            {activeState.articles.map((article) => (
              <ExploreRow
                key={article.id}
                article={article}
                mode={mode}
                onClick={() => openArticle(article.id)}
                state={getOverlay(article.id, {
                  reaction: article.reaction,
                  is_saved: article.is_saved,
                  read_full_article: article.read_full_article,
                })}
              />
            ))}
            {activeState.hasMore && (
              <div
                ref={sentinelRef}
                className="flex justify-center"
                style={{ padding: '8px 0 24px' }}
              >
                {activeState.loadingMore && <Spinner size={22} />}
              </div>
            )}
            {/* Silence the unused-variable lint while still subscribing the
                screen to overlay changes (icons re-render on store updates). */}
            <span style={{ display: 'none' }}>{Object.keys(overrides).length}</span>
          </div>
        )}
      </div>

      <BottomNav />
    </div>
  )
}

// ── Tabs ───────────────────────────────────────────────────────────────────
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
    {(['history', 'new'] as Mode[]).map((m) => {
      const active = m === mode
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
            color: active ? 'var(--accent)' : 'var(--text-tertiary)',
            background: active ? 'var(--accent-subtle)' : 'transparent',
          }}
        >
          {m === 'history' ? 'Lus' : 'Nouveaux'}
        </button>
      )
    })}
  </div>
)

// ── Row ────────────────────────────────────────────────────────────────────
interface RowProps {
  article: Row
  state: FeedbackState
  mode: Mode
  onClick: () => void
}

const ExploreRow = ({ article, state, mode, onClick }: RowProps) => {
  const timeSource =
    mode === 'history' && article.seen_at ? article.seen_at : article.published_at
  return (
    <button
      onClick={onClick}
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
        {/* New tab has no per-article state to show (always defaults) —
            omit the icon row to keep the visual lighter. */}
        {mode === 'history' && <StateIcons state={state} />}
        <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 4 }}>
          {formatTimeAgo(timeSource)}
        </p>
      </div>
    </button>
  )
}

const StateIcons = ({ state }: { state: FeedbackState }) => (
  <div className="flex items-center" style={{ gap: 10 }}>
    <Bookmark
      size={13}
      style={{
        color: state.is_saved ? 'var(--action-save)' : 'var(--text-tertiary)',
        fill: state.is_saved ? 'var(--action-save)' : 'none',
        opacity: state.is_saved ? 1 : 0.5,
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
        opacity: state.reaction === 'like' ? 1 : 0.5,
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
        opacity: state.reaction === 'dislike' ? 1 : 0.5,
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

// ── Per-tab state ──────────────────────────────────────────────────────────
interface TabState<A> {
  status: 'idle' | 'loading' | 'ready' | 'error'
  articles: A[]
  cursor: string | null
  hasMore: boolean
  loadingMore: boolean
  errorMsg: string
}

function emptyTabState<A>(): TabState<A> {
  return {
    status: 'idle',
    articles: [],
    cursor: null,
    hasMore: false,
    loadingMore: false,
    errorMsg: '',
  }
}
