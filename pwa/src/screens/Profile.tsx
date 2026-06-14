import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Rss,
  LogOut,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Activity,
  AlertTriangle,
  RefreshCw,
  Tags,
} from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { Spinner } from '../components/Spinner'
import { useApiData } from '../hooks/useApiData'
import { useAuthStore } from '../store/auth'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import {
  getMe,
  getStats,
  triggerRefresh,
  type PipelineWindow,
  type Stats,
} from '../api'

// E10-S1 — the staleness threshold is now driven by the live
// `cron_fetch_interval_minutes` from /stats; the previous hardcoded constant
// went wrong whenever the admin changed the interval. Helper at the bottom
// of the file derives the threshold per render.
const REFRESH_DEBOUNCE_MS = 60 * 1000
const REFRESH_REFETCH_MS = 10 * 1000

export const Profile = () => {
  const navigate = useNavigate()
  const storedEmail = useAuthStore((s) => s.email)
  const logout = useAuthStore((s) => s.logout)

  // Authoritative counts + email from the server (E7-S9). The auth store's
  // email is only a fallback while the request is in flight.
  const { data: me, loading, reload: reloadMe } = useApiData(getMe, [])
  const email = me?.email ?? storedEmail ?? 'user@example.com'

  // ── System section (E7-S15) ─────────────────────────────────────────────
  const [systemOpen, setSystemOpen] = useState(false)
  const [stats, setStats] = useState<Stats | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshDisabledUntil, setRefreshDisabledUntil] = useState(0)
  // E10-S5 — picker state for the windowed pipeline aggregates. Default
  // 6h matches the backend default and is wide enough to smooth out the
  // 15-min cron cadence (~24 runs) while still reflecting recent state.
  const [pipelineWindow, setPipelineWindow] = useState<PipelineWindow>('6h')

  const loadStats = async (window: PipelineWindow = pipelineWindow) => {
    setStatsLoading(true)
    setStatsError(null)
    try {
      setStats(await getStats(window))
    } catch {
      setStatsError("Couldn't load system stats.")
    } finally {
      setStatsLoading(false)
    }
  }

  // Lazy-load on first expand.
  useEffect(() => {
    if (systemOpen && stats === null && !statsLoading) loadStats()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [systemOpen])

  const handleWindowChange = (next: PipelineWindow) => {
    if (next === pipelineWindow) return
    setPipelineWindow(next)
    // Refetch immediately — /stats is cheap and there's no client-side
    // cache that would benefit from a debounce here.
    loadStats(next)
  }

  const runRefresh = async () => {
    if (refreshing || Date.now() < refreshDisabledUntil) return
    setRefreshing(true)
    try {
      await triggerRefresh()
      setRefreshDisabledUntil(Date.now() + REFRESH_DEBOUNCE_MS)
      // Give the background job a head start, then refetch stats.
      setTimeout(() => loadStats(), REFRESH_REFETCH_MS)
    } catch {
      setStatsError("Couldn't start refresh.")
    } finally {
      setRefreshing(false)
    }
  }

  const initials = email
    .split('@')[0]
    .slice(0, 2)
    .toUpperCase()

  const statRows = [
    { label: 'Saved', value: me?.saved_count, route: '/saved' },
    { label: 'Keywords', value: me?.keyword_count, route: '/keywords' },
    { label: 'Sources', value: me?.source_count, route: '/sources' },
  ]

  const handleSignOut = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex flex-col h-dvh overflow-y-auto relative">
      <BlobBackground onRefresh={reloadMe} />

      <header
        className="relative z-10 flex items-center justify-center"
        style={{ padding: '16px 20px 8px' }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Profile
        </h1>
      </header>

      <div className="relative z-10 flex-1 flex flex-col items-center" style={{ padding: '24px 16px 90px' }}>
        {/* Avatar */}
        <div
          className="flex items-center justify-center"
          style={{
            width: 72,
            height: 72,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, var(--accent), var(--blob-cyan))',
            fontSize: 24,
            fontWeight: 600,
            color: '#0c1018',
            marginBottom: 12,
          }}
        >
          {initials}
        </div>

        <p style={{ fontSize: 15, fontWeight: 600, marginBottom: 2 }}>
          {email.split('@')[0]}
        </p>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 24 }}>
          {email}
        </p>

        {/* Stats — each cell doubles as a shortcut to its detail screen
            (Saved/Keywords/Sources). The matching menu rows below remain so
            users still have a discoverable way in. */}
        <div className="flex gap-3 w-full" style={{ maxWidth: 320, marginBottom: 32 }}>
          {statRows.map((s) => (
            <button
              key={s.label}
              onClick={() => navigate(s.route)}
              className="glass-sm flex-1 flex flex-col items-center"
              style={{
                borderRadius: 16,
                padding: '14px 8px',
                border: '1px solid rgba(255,255,255,0.10)',
                background: 'var(--glass-bg)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
              }}
            >
              <span style={{ fontSize: 18, fontWeight: 600, marginBottom: 2, minHeight: 24 }}>
                {loading ? <Spinner size={14} /> : (s.value ?? '—')}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                {s.label}
              </span>
            </button>
          ))}
        </div>

        {/* Menu */}
        <div className="w-full flex flex-col gap-2" style={{ maxWidth: 320 }}>
          <button
            onClick={() => navigate('/sources')}
            className="glass-sm flex items-center gap-3 w-full"
            style={{
              borderRadius: 16,
              padding: '14px 16px',
              cursor: 'pointer',
              border: '1px solid rgba(255,255,255,0.10)',
              background: 'var(--glass-bg)',
              color: 'var(--text-primary)',
              fontSize: 14,
            }}
          >
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 10,
                background: 'var(--accent-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent)',
              }}
            >
              <Rss size={16} />
            </div>
            <span className="flex-1 text-left">Manage sources</span>
            <ChevronRight size={18} style={{ color: 'var(--text-tertiary)' }} />
          </button>

          {/* Keywords moved here (E9-S4) — out of the BottomNav, into the
              less-used Profile menu where config-style screens live. */}
          <button
            onClick={() => navigate('/keywords')}
            className="glass-sm flex items-center gap-3 w-full"
            style={{
              borderRadius: 16,
              padding: '14px 16px',
              cursor: 'pointer',
              border: '1px solid rgba(255,255,255,0.10)',
              background: 'var(--glass-bg)',
              color: 'var(--text-primary)',
              fontSize: 14,
            }}
          >
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 10,
                background: 'var(--accent-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent)',
              }}
            >
              <Tags size={16} />
            </div>
            <span className="flex-1 text-left">Keywords</span>
            <ChevronRight size={18} style={{ color: 'var(--text-tertiary)' }} />
          </button>

          {me?.is_admin && (
            <button
              onClick={() => navigate('/admin')}
              className="glass-sm flex items-center gap-3 w-full"
              style={{
                borderRadius: 16,
                padding: '14px 16px',
                cursor: 'pointer',
                border: '1px solid rgba(255,255,255,0.10)',
                background: 'var(--glass-bg)',
                color: 'var(--text-primary)',
                fontSize: 14,
              }}
            >
              <div
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 10,
                  background: 'var(--accent-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent)',
                }}
              >
                <Activity size={16} />
              </div>
              <span className="flex-1 text-left">Administration</span>
              <ChevronRight size={18} style={{ color: 'var(--text-tertiary)' }} />
            </button>
          )}

          {/* System (E7-S15) — collapsible health + AI enrichment stats.
              Kept inside the same gap-2 stack as the menu rows for visual
              consistency (E7-S27). */}
          <div>
            <button
              onClick={() => setSystemOpen((o) => !o)}
              className="glass-sm flex items-center gap-3 w-full"
              style={{
                borderRadius: 16,
                padding: '14px 16px',
                cursor: 'pointer',
                border: '1px solid rgba(255,255,255,0.10)',
                background: 'var(--glass-bg)',
                color: 'var(--text-primary)',
                fontSize: 14,
              }}
              aria-expanded={systemOpen}
            >
              <div
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 10,
                  background: 'var(--accent-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent)',
                }}
              >
                <Activity size={16} />
              </div>
              <span className="flex-1 text-left">System</span>
              {systemOpen ? (
                <ChevronUp size={18} style={{ color: 'var(--text-tertiary)' }} />
              ) : (
                <ChevronDown size={18} style={{ color: 'var(--text-tertiary)' }} />
              )}
            </button>

            {systemOpen && (
              <SystemPanel
                stats={stats}
                loading={statsLoading}
                error={statsError}
                onRetry={() => loadStats()}
                refreshing={refreshing}
                refreshDisabled={Date.now() < refreshDisabledUntil}
                onRefresh={runRefresh}
                pipelineWindow={pipelineWindow}
                onPipelineWindowChange={handleWindowChange}
              />
            )}
          </div>

          {/* Sign out lives at the very bottom of the Profile menu so it
              never sits between non-destructive options (E10-S2 UX pass). */}
          <button
            onClick={handleSignOut}
            className="glass-sm flex items-center gap-3 w-full"
            style={{
              borderRadius: 16,
              padding: '14px 16px',
              cursor: 'pointer',
              border: '1px solid rgba(255,255,255,0.10)',
              background: 'var(--glass-bg)',
              color: 'var(--text-primary)',
              fontSize: 14,
            }}
          >
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 10,
                background: 'rgba(248, 113, 113, 0.10)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--action-dislike)',
              }}
            >
              <LogOut size={16} />
            </div>
            <span className="flex-1 text-left">Sign out</span>
            <ChevronRight size={18} style={{ color: 'var(--text-tertiary)' }} />
          </button>
        </div>
      </div>

      <BottomNav />
    </div>
  )
}

interface SystemPanelProps {
  stats: Stats | null
  loading: boolean
  error: string | null
  onRetry: () => void
  refreshing: boolean
  refreshDisabled: boolean
  onRefresh: () => void
  pipelineWindow: PipelineWindow
  onPipelineWindowChange: (next: PipelineWindow) => void
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

type AiStatus = 'working' | 'failed' | 'off'

function aiStatus(enrichment: Stats['enrichment']): AiStatus {
  const { total_ai, total_tfidf_fallback, last_error, last_error_at, last_enriched_at } = enrichment
  if (total_ai === 0 && total_tfidf_fallback === 0) return 'off'
  if (!last_error) return 'working'
  // last_error present: failed iff the error is at least as recent as the
  // last successful enrichment (or no successful run yet).
  if (!last_enriched_at) return 'failed'
  if (!last_error_at) return 'working'
  return new Date(last_error_at) >= new Date(last_enriched_at) ? 'failed' : 'working'
}

// E10-S7 — OpenRouter costs are typically fractions of a cent; 4 decimals
// keeps small-but-nonzero amounts visible instead of rounding to "$0.00".
function formatCost(usd: number): string {
  if (usd === 0) return '$0'
  if (usd < 0.0001) return '< $0.0001'
  return `$${usd.toFixed(4)}`
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const mins = Math.floor(seconds / 60)
  const rest = Math.round(seconds - mins * 60)
  return rest === 0 ? `${mins}m` : `${mins}m ${rest}s`
}

function nextRunLabel(
  pipeline: Stats['pipeline'],
  intervalMinutes: number,
): string {
  // While a run is in flight, no countdown is meaningful — show its live
  // state. The CronTrigger won't fire again until the lock is released.
  if (pipeline.status === 'running') return 'en cours'
  if (intervalMinutes <= 0) return '—'
  // Anchor on completed_at when available: a slow run that took longer than
  // the interval would otherwise report "soon" while the wall-clock
  // CronTrigger hasn't fired yet (E10-S1 review). Fall back to started_at
  // for transitional rows that lack completed_at (e.g. abruptly killed runs
  // still tagged 'running' in DB).
  const anchor = pipeline.completed_at ?? pipeline.started_at
  if (!anchor) return '—'
  const due = new Date(anchor).getTime() + intervalMinutes * 60_000
  const diffMs = due - Date.now()
  if (diffMs <= 0) return 'soon'
  const mins = Math.max(1, Math.round(diffMs / 60_000))
  return `in ~${mins} min`
}

// E10-S1: stalled iff the latest *completed* run is older than 2× the cron
// interval. A run currently in flight is never stalled, even if long. Never
// flag a fresh install with no recorded run.
function isStalled(pipeline: Stats['pipeline'], intervalMinutes: number): boolean {
  if (pipeline.status !== 'completed' || !pipeline.completed_at) return false
  const ageMs = Date.now() - new Date(pipeline.completed_at).getTime()
  return ageMs > 2 * intervalMinutes * 60_000
}

const SystemPanel = ({
  stats,
  loading,
  error,
  onRetry,
  refreshing,
  refreshDisabled,
  onRefresh,
  pipelineWindow,
  onPipelineWindowChange,
}: SystemPanelProps) => {
  if (loading && !stats) {
    return (
      <div className="flex justify-center" style={{ padding: '16px 0' }}>
        <Spinner size={18} />
      </div>
    )
  }
  if (error) {
    return (
      <div
        className="glass-sm"
        style={{
          borderRadius: 12,
          padding: '12px 14px',
          marginTop: 8,
          fontSize: 12,
          color: 'var(--text-secondary)',
        }}
      >
        <p style={{ margin: '0 0 8px' }}>{error}</p>
        <button
          onClick={onRetry}
          style={{
            fontSize: 12,
            color: 'var(--accent-text)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          Retry
        </button>
      </div>
    )
  }
  if (!stats) return null

  const { pipeline } = stats
  const interval = stats.cron_fetch_interval_minutes
  const stale = isStalled(pipeline, interval)
  const status = aiStatus(stats.enrichment)
  const running = pipeline.status === 'running'

  return (
    <div
      className="glass-sm"
      style={{
        borderRadius: 12,
        padding: '12px 14px',
        marginTop: 8,
        fontSize: 12,
        color: 'var(--text-secondary)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <Row label="Prochain run">
        <span>{nextRunLabel(pipeline, interval)}</span>
      </Row>
      <Row label="Articles en attente">
        <span>{stats.articles.pending_enrichment}</span>
      </Row>
      <Row label="Statut IA">
        <AiStatusPill status={status} />
      </Row>

      {/* In-progress bar — kept above the aggregates block (E10-S5): it
          is live and run-scoped, distinct from the historical window. */}
      {running && pipeline.in_progress && (
        <ProgressBar
          done={pipeline.in_progress.done}
          total={pipeline.in_progress.total}
        />
      )}

      {/* Windowed aggregates (E10-S5) — replaces the old single-run
          summary so a 1-2 article cycle no longer dominates the panel. */}
      <PipelineAggregatesBlock
        aggregates={pipeline.aggregates}
        selected={pipelineWindow}
        onSelect={onPipelineWindowChange}
        disabled={loading}
      />

      {/* OpenRouter bill over 1h/6h/24h (E10-S7). */}
      <LlmCostBlock windows={stats.llm_cost.windows} />

      {stale && (
        <Warning>
          Feed may be stalled — last run finished{' '}
          {pipeline.completed_at ? formatTimeAgo(pipeline.completed_at) : 'a while'}{' '}
          ago.
        </Warning>
      )}

      {/* Pipeline error — surfaced from pipeline_runs.error, no longer gated
          on the AI fallback heuristic (E10-S1). */}
      {pipeline.error && (
        <Warning>
          <strong style={{ fontWeight: 600 }}>Pipeline error</strong>
          <span
            style={{ display: 'block', marginTop: 2 }}
            title={pipeline.error}
          >
            {truncate(pipeline.error, 80)}
          </span>
          {pipeline.completed_at && (
            <span
              style={{
                display: 'block',
                marginTop: 2,
                color: 'var(--text-tertiary)',
              }}
              title={pipeline.completed_at}
            >
              {formatTimeAgo(pipeline.completed_at)}
            </span>
          )}
        </Warning>
      )}

      {stats.enrichment.last_error && (
        <Warning>
          <strong style={{ fontWeight: 600 }}>Enrichment error</strong>
          <span
            style={{ display: 'block', marginTop: 2 }}
            title={stats.enrichment.last_error}
          >
            {truncate(stats.enrichment.last_error, 80)}
          </span>
          {stats.enrichment.last_error_at && (
            <span
              style={{
                display: 'block',
                marginTop: 2,
                color: 'var(--text-tertiary)',
              }}
              title={stats.enrichment.last_error_at}
            >
              {formatTimeAgo(stats.enrichment.last_error_at)}
            </span>
          )}
        </Warning>
      )}

      {/* Run now (E7-S16) */}
      <button
        onClick={onRefresh}
        disabled={refreshing || refreshDisabled}
        className="flex items-center justify-center gap-2"
        style={{
          marginTop: 4,
          padding: '8px 12px',
          borderRadius: 10,
          border: '1px solid var(--accent-border)',
          background: 'var(--accent-subtle)',
          color: 'var(--accent-text)',
          fontSize: 12,
          fontWeight: 600,
          cursor: refreshing || refreshDisabled ? 'default' : 'pointer',
          opacity: refreshing || refreshDisabled ? 0.6 : 1,
        }}
      >
        {refreshing ? (
          <Spinner size={12} />
        ) : (
          <RefreshCw size={12} />
        )}
        {refreshing ? 'Starting…' : refreshDisabled ? 'Triggered' : 'Run now'}
      </button>
    </div>
  )
}

const ProgressBar = ({ done, total }: { done: number; total: number }) => {
  const ratio = total > 0 ? Math.min(1, done / total) : 0
  return (
    <div
      role="status"
      aria-live="polite"
      style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 11,
          color: 'var(--text-tertiary)',
        }}
      >
        <span>Enrichissement en cours</span>
        <span>
          {done} / {total} articles
        </span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 999,
          background: 'rgba(255,255,255,0.08)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${ratio * 100}%`,
            height: '100%',
            background: 'var(--accent)',
            transition: 'width 200ms ease-out',
          }}
        />
      </div>
    </div>
  )
}

const PIPELINE_WINDOW_OPTIONS: PipelineWindow[] = ['1h', '6h', '24h']

const PipelineAggregatesBlock = ({
  aggregates,
  selected,
  onSelect,
  disabled,
}: {
  aggregates: Stats['pipeline']['aggregates']
  selected: PipelineWindow
  onSelect: (next: PipelineWindow) => void
  disabled: boolean
}) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      paddingTop: 4,
      borderTop: '1px solid rgba(255,255,255,0.06)',
    }}
  >
    <div
      className="flex items-center justify-between"
      style={{ gap: 8, flexWrap: 'wrap' }}
    >
      <span style={{ color: 'var(--text-tertiary)' }}>Pipeline · Last</span>
      <div
        role="group"
        aria-label="Pipeline window"
        style={{ display: 'inline-flex', gap: 4 }}
      >
        {PIPELINE_WINDOW_OPTIONS.map((w) => {
          const active = w === selected
          return (
            <button
              key={w}
              type="button"
              aria-pressed={active}
              disabled={disabled}
              onClick={() => onSelect(w)}
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: 999,
                border: active
                  ? '1px solid var(--accent-border)'
                  : '1px solid rgba(255,255,255,0.10)',
                background: active ? 'var(--accent-subtle)' : 'transparent',
                color: active ? 'var(--accent-text)' : 'var(--text-secondary)',
                cursor: disabled ? 'default' : 'pointer',
                opacity: disabled ? 0.6 : 1,
              }}
            >
              {w}
            </button>
          )
        })}
      </div>
    </div>
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '4px 10px',
        fontSize: 11,
        color: 'var(--text-tertiary)',
      }}
    >
      <span>
        {aggregates.runs_count} run
        {aggregates.runs_count === 1 ? '' : 's'}
      </span>
      <span>·</span>
      <span>{aggregates.articles_fetched} fetched</span>
      <span>·</span>
      <span>{aggregates.articles_enriched} enrichis</span>
      {aggregates.articles_failed > 0 && (
        <>
          <span>·</span>
          <span style={{ color: 'var(--action-save)' }}>
            {aggregates.articles_failed} erreur
            {aggregates.articles_failed > 1 ? 's' : ''}
          </span>
        </>
      )}
      {aggregates.avg_s_per_article !== null && (
        <>
          <span>·</span>
          <span>~{formatDuration(aggregates.avg_s_per_article)}/article</span>
        </>
      )}
    </div>
  </div>
)

const LlmCostBlock = ({ windows }: { windows: Stats['llm_cost']['windows'] }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      paddingTop: 4,
      borderTop: '1px solid rgba(255,255,255,0.06)',
    }}
  >
    <span style={{ color: 'var(--text-tertiary)' }}>Coût OpenRouter</span>
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '4px 12px',
        fontSize: 11,
        color: 'var(--text-secondary)',
      }}
    >
      {windows.map((w) => (
        <span key={w.window_hours}>
          {w.window_hours}h · {formatCost(w.cost_usd)}
        </span>
      ))}
    </div>
  </div>
)

const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex items-center justify-between">
    <span style={{ color: 'var(--text-tertiary)' }}>{label}</span>
    <span style={{ color: 'var(--text-secondary)' }}>{children}</span>
  </div>
)

const AiStatusPill = ({ status }: { status: AiStatus }) => {
  const config = {
    working: { dot: '#22c55e', label: 'AI · Working' },
    failed: { dot: '#f9c74f', label: 'AI · Last run failed' },
    off: { dot: 'var(--text-tertiary)', label: 'AI · Off (TF-IDF)' },
  }[status]
  return (
    <span className="flex items-center gap-1.5">
      <span
        aria-hidden
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: config.dot,
          display: 'inline-block',
        }}
      />
      {config.label}
    </span>
  )
}

const Warning = ({ children }: { children: React.ReactNode }) => (
  <div
    className="flex items-start gap-2"
    role="alert"
    style={{
      padding: '8px 10px',
      borderRadius: 10,
      background: 'rgba(249, 199, 79, 0.10)',
      border: '1px solid rgba(249, 199, 79, 0.25)',
      color: 'var(--text-secondary)',
    }}
  >
    <AlertTriangle
      size={14}
      style={{ color: 'var(--action-save)', flexShrink: 0, marginTop: 1 }}
    />
    <div style={{ fontSize: 11, lineHeight: 1.4 }}>{children}</div>
  </div>
)
