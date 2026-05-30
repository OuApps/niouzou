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
} from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { Spinner } from '../components/Spinner'
import { useApiData } from '../hooks/useApiData'
import { useAuthStore } from '../store/auth'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { getMe, getStats, triggerRefresh, type Stats } from '../api'

// Server default cron_fetch interval is 15 min — staleness warning fires past
// 2× that (E7-S15). PWA doesn't know the real interval; this matches docs.
const STALE_AFTER_MS = 30 * 60 * 1000
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

  const loadStats = async () => {
    setStatsLoading(true)
    setStatsError(null)
    try {
      setStats(await getStats())
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

  const runRefresh = async () => {
    if (refreshing || Date.now() < refreshDisabledUntil) return
    setRefreshing(true)
    try {
      await triggerRefresh()
      setRefreshDisabledUntil(Date.now() + REFRESH_DEBOUNCE_MS)
      // Give the background job a head start, then refetch stats.
      setTimeout(loadStats, REFRESH_REFETCH_MS)
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
    { label: 'Saved', value: me?.saved_count },
    { label: 'Keywords', value: me?.keyword_count },
    { label: 'Sources', value: me?.source_count },
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

        {/* Stats */}
        <div className="flex gap-3 w-full" style={{ maxWidth: 320, marginBottom: 32 }}>
          {statRows.map((s) => (
            <div
              key={s.label}
              className="glass-sm flex-1 flex flex-col items-center"
              style={{ borderRadius: 16, padding: '14px 8px' }}
            >
              <span style={{ fontSize: 18, fontWeight: 600, marginBottom: 2, minHeight: 24 }}>
                {loading ? <Spinner size={14} /> : (s.value ?? '—')}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                {s.label}
              </span>
            </div>
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

        {/* System (E7-S15) — collapsible health + AI enrichment stats */}
        <div className="w-full" style={{ maxWidth: 320, marginTop: 24 }}>
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
              onRetry={loadStats}
              refreshing={refreshing}
              refreshDisabled={Date.now() < refreshDisabledUntil}
              onRefresh={runRefresh}
            />
          )}
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
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

const SystemPanel = ({
  stats,
  loading,
  error,
  onRetry,
  refreshing,
  refreshDisabled,
  onRefresh,
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

  const fetchedAt = stats.articles.last_fetched_at
  const stale =
    fetchedAt !== null &&
    Date.now() - new Date(fetchedAt).getTime() > STALE_AFTER_MS
  const hasFallback = stats.enrichment.total_tfidf_fallback > 0

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
      {/* Cron health */}
      <Row label="Last fetch">
        <span title={fetchedAt ?? ''}>
          {fetchedAt ? formatTimeAgo(fetchedAt) : '—'}
        </span>
      </Row>
      <Row label="Last enrichment">
        <span title={stats.enrichment.last_enriched_at ?? ''}>
          {stats.enrichment.last_enriched_at
            ? formatTimeAgo(stats.enrichment.last_enriched_at)
            : '—'}
        </span>
      </Row>
      <Row label="Pending enrichment">
        <span>{stats.articles.pending_enrichment}</span>
      </Row>

      {stale && (
        <Warning>
          Feed may be stalled — last fetch was{' '}
          {fetchedAt ? formatTimeAgo(fetchedAt) : 'a while'} ago.
        </Warning>
      )}

      {/* AI stats */}
      <div
        style={{
          marginTop: 4,
          paddingTop: 8,
          borderTop: '1px solid var(--divider)',
          color: 'var(--text-tertiary)',
        }}
      >
        {stats.enrichment.total_ai} with AI · {stats.enrichment.total_tfidf} with TF-IDF
        {stats.enrichment.total_tfidf_fallback > 0 && (
          <span> (incl. {stats.enrichment.total_tfidf_fallback} fallback)</span>
        )}
      </div>

      {hasFallback && stats.enrichment.last_error && (
        <Warning>
          <strong style={{ fontWeight: 600 }}>Last error</strong>
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

const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex items-center justify-between">
    <span style={{ color: 'var(--text-tertiary)' }}>{label}</span>
    <span style={{ color: 'var(--text-secondary)' }}>{children}</span>
  </div>
)

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
