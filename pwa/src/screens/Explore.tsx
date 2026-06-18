import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Compass, Search, X } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ArticleListRow } from '../components/ArticleListRow'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { FilterChip } from '../components/FilterChip'
import { useInfiniteScroll } from '../hooks/useInfiniteScroll'
import {
  ApiError,
  getExploreHistory,
  getExploreNew,
  getExploreSearch,
  getSources,
  getStats,
  type ExploreHistoryArticle,
  type ExploreOptions,
} from '../api'
import { tokens } from '../api/http'
import type { FeedArticle, SourceFull } from '../types/api'

const PAGE_SIZE = 20
// E17-S3 — search below this many characters is too broad (mirrors the API).
const MIN_SEARCH_CHARS = 2
const SEARCH_DEBOUNCE_MS = 300

type Mode = 'history' | 'new'

// Both endpoints return a `FeedArticle`; History adds `seen_at`. We carry the
// optional field on the row type so the component can render `seen_at` when
// available and `published_at` otherwise.
type Row = FeedArticle & { seen_at?: string }

// E11-S2 — fixed score chips (in this order). Default is the threshold value.
// The "gteThreshold" chip's effective value comes from /stats.score_threshold.
type ScoreChipKind = 'gte0' | 'gte25' | 'gte50' | 'gteThreshold' | 'gte75'

interface ScoreChip {
  kind: ScoreChipKind
  value: number | null
}

const SCORE_CHIPS: ScoreChip[] = [
  { kind: 'gte0', value: 0 },
  { kind: 'gte25', value: 0.25 },
  { kind: 'gte50', value: 0.5 },
  { kind: 'gteThreshold', value: null },
  { kind: 'gte75', value: 0.75 },
]

const formatPct = (v: number) => `${Math.round(v * 100)} %`

// Per-tab filter state. Each tab keeps its own selection so switching back
// preserves what the user had.
interface Filters {
  scoreKind: ScoreChipKind
  // Selected source UUIDs. Empty array means "Toutes".
  sourceIds: string[]
}

// Explore "Nouveaux" is the unfiltered scan of the queue (explore_service:
// no score gate), so the score chips default to "show everything" (≥ 0). The
// "≥ seuil" chip stays available for users who want the feed's threshold.
const DEFAULT_FILTERS: Filters = { scoreKind: 'gte0', sourceIds: [] }

interface TabState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  articles: Row[]
  cursor: string | null
  hasMore: boolean
  loadingMore: boolean
  errorMsg: string
  filters: Filters
}

const EMPTY: TabState = {
  status: 'idle',
  articles: [],
  cursor: null,
  hasMore: false,
  loadingMore: false,
  errorMsg: '',
  filters: DEFAULT_FILTERS,
}

// UX — opening an article navigates to the Feed (`/?start=`), which unmounts
// Explore. This snapshot survives that round-trip so coming back restores the
// active tab, its filters, the already-loaded rows and the scroll position
// instead of resetting to a fresh "Nouveaux" scan.
//
// It lives in `sessionStorage`, not a module variable: on mobile the back
// gesture (swipe from the screen edge) frequently triggers a *full document
// reload* of /explore rather than an SPA popstate, which would wipe any
// in-memory state. The write happens during the reliable SPA unmount
// (Explore → Feed), and the read happens on Explore boot — so restoration
// works whether the user comes back via popstate or a hard reload.
// Session-scoped: cleared when the tab closes, overwritten by pull-to-refresh.
const SNAPSHOT_KEY = 'niouzou_explore_snapshot'

interface ExploreSnapshot {
  // Owner (user email) the snapshot was taken for. A second user logging in on
  // the same tab must not see the previous user's rows; a mismatch is treated
  // as "no snapshot".
  owner: string | null
  mode: Mode
  tabs: Record<Mode, TabState>
  scrollTop: number
  // E17-S3 — active search query, so opening a result and coming back keeps
  // the user in their search rather than dropping them on the tabs.
  query?: string
}

const readSnapshot = (): ExploreSnapshot | null => {
  try {
    const raw = sessionStorage.getItem(SNAPSHOT_KEY)
    if (!raw) return null
    const snap = JSON.parse(raw) as ExploreSnapshot
    return snap.owner === tokens.email() ? snap : null
  } catch {
    return null
  }
}

const writeSnapshot = (snap: ExploreSnapshot) => {
  try {
    sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snap))
  } catch {
    // Quota or serialization failure — non-critical, just lose restoration.
  }
}

const FETCHERS: Record<Mode, (opts: ExploreOptions) => Promise<{
  articles: (FeedArticle | ExploreHistoryArticle)[]
  next_cursor: string | null
  has_more: boolean
}>> = {
  history: getExploreHistory,
  new: getExploreNew,
}

const resolveMinScore = (
  filters: Filters,
  threshold: number | null,
): number | undefined => {
  switch (filters.scoreKind) {
    case 'gte0':
      return 0
    case 'gte25':
      return 0.25
    case 'gte50':
      return 0.5
    case 'gte75':
      return 0.75
    case 'gteThreshold':
      // Threshold chip's value comes from /stats — guard to avoid NaN.
      return threshold && threshold > 0 ? threshold : undefined
  }
}

export const Explore = () => {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>(() => readSnapshot()?.mode ?? 'new')
  const [tabs, setTabs] = useState<Record<Mode, TabState>>(
    () => readSnapshot()?.tabs ?? { history: EMPTY, new: EMPTY },
  )
  // E17-S3 — text search. When the query reaches MIN_SEARCH_CHARS the results
  // replace the tab view (tabs + filters are hidden while searching).
  const [searchQuery, setSearchQuery] = useState(() => readSnapshot()?.query ?? '')
  const [search, setSearch] = useState<TabState>(EMPTY)
  // Bumped to force the search effect to re-run on retry (same query string).
  const [searchNonce, setSearchNonce] = useState(0)
  const searching = searchQuery.trim().length >= MIN_SEARCH_CHARS
  // E17-S6 — search ignores the Explore filters entirely (no score/source
  // gate), so we hide the tabs + filter bar as soon as the user starts typing,
  // not only once the query is long enough to actually run (MIN_SEARCH_CHARS).
  const typing = searchQuery.trim().length > 0
  const loadingMoreRef = useRef(false)
  // The scroll container — read on unmount and re-applied on remount so the
  // user lands back where they left off after opening an article.
  const scrollRef = useRef<HTMLDivElement | null>(null)
  // E17-S6 — the search query is only carried across the unmount when the user
  // is opening an article (so returning keeps them in their search). Leaving
  // Explore any other way (bottom-nav to Feed/Saved) clears the field.
  const openingArticleRef = useRef(false)

  // Sources + score threshold are mount-time fetches kept on refs so the
  // chip bar renders even before /stats has resolved (chip simply hides).
  const [sources, setSources] = useState<SourceFull[] | null>(null)
  const [scoreThreshold, setScoreThreshold] = useState<number | null>(null)

  const active = tabs[mode]

  // Keep the latest state reachable from the unmount cleanup below without
  // re-running the effect (which would clobber the restored scroll position).
  const latest = useRef({ mode, tabs, query: searchQuery })
  useEffect(() => {
    latest.current = { mode, tabs, query: searchQuery }
  })

  useLayoutEffect(() => {
    // Restore the scroll position captured before navigating to an article.
    // useLayoutEffect runs after the cached rows are in the DOM but before
    // paint, so the jump isn't visible.
    const el = scrollRef.current
    const restored = readSnapshot()
    if (restored && el) el.scrollTop = restored.scrollTop
    return () => {
      // `el` is the same container node for the component's whole life, so its
      // scrollTop at cleanup time is the position the user is leaving on. This
      // cleanup runs on the SPA unmount when opening an article, so the
      // snapshot is persisted before any subsequent reload.
      writeSnapshot({
        owner: tokens.email(),
        mode: latest.current.mode,
        tabs: latest.current.tabs,
        scrollTop: el?.scrollTop ?? 0,
        // Only preserve the search across an article round-trip; any other exit
        // (bottom-nav) drops it so Explore reopens on a clean field.
        query: openingArticleRef.current ? latest.current.query : undefined,
      })
    }
  }, [])

  const patch = useCallback((target: Mode, change: Partial<TabState>) => {
    setTabs((prev) => ({ ...prev, [target]: { ...prev[target], ...change } }))
  }, [])

  const fetchFirstPage = useCallback(
    async (target: Mode, filters: Filters) => {
      patch(target, { status: 'loading', filters })
      try {
        const page = await FETCHERS[target]({
          limit: PAGE_SIZE,
          minScore: resolveMinScore(filters, scoreThreshold),
          sourceIds: filters.sourceIds,
        })
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
    [patch, scoreThreshold],
  )

  // Mount-time fetches. Sources is a one-shot lookup; stats is read once for
  // the threshold value (refreshed on pull-to-refresh below).
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [s, st] = await Promise.all([getSources(), getStats()])
        if (cancelled) return
        setSources(s.sources)
        setScoreThreshold(st.score_threshold)
      } catch {
        // Filter bar still works without these — the threshold chip just
        // stays hidden and the sources row shows nothing extra.
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // Initial load of the active tab (and lazy-load on tab switch).
  useEffect(() => {
    if (active.status === 'idle') fetchFirstPage(mode, active.filters)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  const reload = useCallback(() => {
    // Pull-to-refresh resets both tabs' filters and refetches the active one.
    setTabs({ history: EMPTY, new: EMPTY })
    fetchFirstPage(mode, DEFAULT_FILTERS)
  }, [fetchFirstPage, mode])

  const applyFilters = useCallback(
    (next: Filters) => {
      // New cursor on every filter change — the keyset would otherwise drag
      // in irrelevant ranks from the previous filter state.
      patch(mode, {
        articles: [],
        cursor: null,
        hasMore: false,
        filters: next,
      })
      fetchFirstPage(mode, next)
    },
    [fetchFirstPage, mode, patch],
  )

  const onScoreChip = useCallback(
    (kind: ScoreChipKind) => {
      if (active.filters.scoreKind === kind) return
      applyFilters({ ...active.filters, scoreKind: kind })
    },
    [active.filters, applyFilters],
  )

  const onSourceChip = useCallback(
    (id: string) => {
      // Multi-select: click to toggle individual source in/out.
      // Empty array = all sources (no filter).
      const current = active.filters.sourceIds
      const next = current.includes(id)
        ? current.filter((x) => x !== id)
        : [...current, id]
      applyFilters({ ...active.filters, sourceIds: next })
    },
    [active.filters, applyFilters],
  )

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !active.hasMore || !active.cursor) return
    loadingMoreRef.current = true
    patch(mode, { loadingMore: true })
    try {
      const page = await FETCHERS[mode]({
        cursor: active.cursor,
        limit: PAGE_SIZE,
        minScore: resolveMinScore(active.filters, scoreThreshold),
        sourceIds: active.filters.sourceIds,
      })
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
  }, [active.cursor, active.filters, active.hasMore, mode, patch, scoreThreshold])

  // E17-S3 — debounced search. Refetches the first page whenever the (trimmed)
  // query changes; a query under MIN_SEARCH_CHARS resets to the idle tab view.
  useEffect(() => {
    const q = searchQuery.trim()
    if (q.length < MIN_SEARCH_CHARS) {
      setSearch(EMPTY)
      return
    }
    let cancelled = false
    setSearch((s) => ({ ...s, status: 'loading' }))
    const timer = setTimeout(async () => {
      try {
        const page = await getExploreSearch(q, undefined, PAGE_SIZE)
        if (cancelled) return
        setSearch({
          status: 'ready',
          articles: page.articles as Row[],
          cursor: page.next_cursor,
          hasMore: page.has_more,
          loadingMore: false,
          errorMsg: '',
          filters: DEFAULT_FILTERS,
        })
      } catch (e) {
        if (cancelled) return
        setSearch((s) => ({
          ...s,
          status: 'error',
          errorMsg: e instanceof ApiError ? e.message : 'La recherche a échoué.',
        }))
      }
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [searchQuery, searchNonce])

  const searchLoadMore = useCallback(async () => {
    if (loadingMoreRef.current || !search.hasMore || !search.cursor) return
    loadingMoreRef.current = true
    setSearch((s) => ({ ...s, loadingMore: true }))
    try {
      const page = await getExploreSearch(
        searchQuery.trim(),
        search.cursor,
        PAGE_SIZE,
      )
      setSearch((s) => ({
        ...s,
        articles: [...s.articles, ...(page.articles as Row[])],
        cursor: page.next_cursor,
        hasMore: page.has_more,
        loadingMore: false,
      }))
    } catch {
      setSearch((s) => ({ ...s, loadingMore: false }))
    } finally {
      loadingMoreRef.current = false
    }
  }, [search.cursor, search.hasMore, searchQuery])

  // The view actually rendered: search results take over when searching.
  const view = searching ? search : active

  const sentinelRef = useInfiniteScroll({
    hasMore: view.hasMore,
    enabled: view.status === 'ready',
    onLoadMore: searching ? searchLoadMore : loadMore,
  })

  const openArticle = useCallback(
    (id: string) => {
      // Flag the impending unmount as an article open so the cleanup keeps the
      // search query in the snapshot (see openingArticleRef).
      openingArticleRef.current = true
      navigate(`/?start=${encodeURIComponent(id)}`)
    },
    [navigate],
  )

  const hasActiveFilters =
    active.filters.scoreKind !== 'gte0' || active.filters.sourceIds.length > 0
  // Disabled sources no longer feed articles — don't clutter the filter bar.
  const activeSources = sources?.filter((s) => s.active) ?? null
  // The sources row is suppressed entirely when the user has 0 or 1 source —
  // filtering a single source down to itself is meaningless.
  const showSourcesRow = (activeSources?.length ?? 0) > 1
  const showThresholdChip = scoreThreshold !== null && scoreThreshold > 0

  return (
    <div ref={scrollRef} className="flex flex-col h-dvh overflow-y-auto relative">
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
        <SearchBox
          value={searchQuery}
          onChange={setSearchQuery}
          onClear={() => setSearchQuery('')}
        />
        {!typing && <Tabs mode={mode} onChange={setMode} />}
      </header>

      {!typing && (
      <div
        className="relative z-10"
        style={{ padding: '8px 0 4px', display: 'flex', flexDirection: 'column', gap: 6 }}
      >
        <ChipRow label="Score :">
          {SCORE_CHIPS.map((chip) => {
            if (chip.kind === 'gteThreshold' && !showThresholdChip) return null
            const label =
              chip.kind === 'gteThreshold'
                ? `≥ ${formatPct(scoreThreshold ?? 0)}`
                : `≥ ${formatPct(chip.value ?? 0)}`
            return (
              <FilterChip
                key={chip.kind}
                label={label}
                active={active.filters.scoreKind === chip.kind}
                onClick={() => onScoreChip(chip.kind)}
              />
            )
          })}
        </ChipRow>

        {showSourcesRow && activeSources && (
          <ChipRow label="Sources :">
            {activeSources.map((s) => (
              <FilterChip
                key={s.id}
                label={s.name.length > 18 ? `${s.name.slice(0, 17)}…` : s.name}
                active={active.filters.sourceIds.length === 0 || active.filters.sourceIds.includes(s.id)}
                onClick={() => onSourceChip(s.id)}
              />
            ))}
          </ChipRow>
        )}
      </div>
      )}

      <div className="relative z-10 flex-1" style={{ padding: '8px 16px 90px' }}>
        {view.status === 'loading' || view.status === 'idle' ? (
          <div className="flex justify-center" style={{ paddingTop: 60 }}>
            <Spinner size={30} />
          </div>
        ) : view.status === 'error' ? (
          <ErrorState
            message={view.errorMsg}
            onRetry={searching ? () => setSearchNonce((n) => n + 1) : reload}
          />
        ) : view.articles.length === 0 ? (
          searching ? (
            <EmptyState
              icon={Search}
              title="Aucun résultat"
              description={`Aucun article ne correspond à « ${searchQuery.trim()} ».`}
            />
          ) : hasActiveFilters ? (
            <FilteredEmptyState
              onReset={() => applyFilters(DEFAULT_FILTERS)}
            />
          ) : (
            <EmptyState
              icon={Compass}
              title={mode === 'history' ? 'Aucun article lu' : 'Pas de nouveaux articles'}
              description={
                mode === 'history'
                  ? 'Reviens ici après avoir parcouru ton feed pour retrouver les articles déjà vus.'
                  : 'Reviens plus tard — le prochain enrichissement va apporter de nouveaux articles.'
              }
            />
          )
        ) : (
          <div className="flex flex-col gap-3">
            {view.articles.map((article) => (
              <ArticleListRow
                key={article.id}
                article={article}
                timestamp={
                  article.seen_at ? article.seen_at : article.published_at
                }
                onClick={() => openArticle(article.id)}
                // History + search reflect per-article state; New is always
                // default, so we hide the icon row to keep the visual lighter.
                showState={searching || mode === 'history'}
              />
            ))}
            {view.hasMore && (
              <div
                ref={sentinelRef}
                className="flex justify-center"
                style={{ padding: '8px 0 24px' }}
              >
                {view.loadingMore && <Spinner size={22} />}
              </div>
            )}
          </div>
        )}
      </div>

      <BottomNav />
    </div>
  )
}

// E17-S3 — full-width search field under the title. Glass-styled to match the
// filter chips; shows a clear (×) button once there's text.
const SearchBox = ({
  value,
  onChange,
  onClear,
}: {
  value: string
  onChange: (v: string) => void
  onClear: () => void
}) => (
  <div
    className="flex items-center"
    style={{
      width: '100%',
      gap: 8,
      padding: '0 12px',
      height: 38,
      borderRadius: 20,
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.08)',
    }}
  >
    <Search size={15} style={{ color: 'var(--text-tertiary)', flex: '0 0 auto' }} />
    <input
      type="search"
      inputMode="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Rechercher un article…"
      aria-label="Rechercher un article"
      style={{
        flex: '1 1 auto',
        minWidth: 0,
        border: 'none',
        outline: 'none',
        background: 'transparent',
        color: 'var(--text-primary)',
        fontSize: 13,
      }}
    />
    {value.length > 0 && (
      <button
        type="button"
        onClick={onClear}
        aria-label="Effacer la recherche"
        style={{
          flex: '0 0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          background: 'transparent',
          color: 'var(--text-tertiary)',
          cursor: 'pointer',
          padding: 2,
        }}
      >
        <X size={15} />
      </button>
    )}
  </div>
)

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

const ChipRow = ({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) => (
  <div
    className="flex items-center"
    style={{ gap: 8, padding: '0 16px', minHeight: 28 }}
  >
    <span
      style={{
        fontSize: 10,
        fontWeight: 600,
        color: 'var(--text-tertiary)',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
        flex: '0 0 auto',
      }}
    >
      {label}
    </span>
    <div
      className="flex"
      style={{
        gap: 6,
        overflowX: 'auto',
        flex: '1 1 auto',
        // Hide scrollbar visually but keep horizontal swipe.
        scrollbarWidth: 'none',
      }}
    >
      {children}
    </div>
  </div>
)

const FilteredEmptyState = ({ onReset }: { onReset: () => void }) => (
  <div
    className="flex flex-col items-center"
    style={{ paddingTop: 60, gap: 12 }}
  >
    <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
      Aucun résultat avec ces filtres.
    </p>
    <button
      type="button"
      onClick={onReset}
      style={{
        padding: '8px 16px',
        borderRadius: 20,
        border: '1px solid var(--accent)',
        background: 'var(--accent-subtle)',
        color: 'var(--accent)',
        fontSize: 12,
        fontWeight: 600,
        cursor: 'pointer',
      }}
    >
      Réinitialiser les filtres
    </button>
  </div>
)
