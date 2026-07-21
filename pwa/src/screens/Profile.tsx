import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Rss,
  LogOut,
  ChevronRight,
  Activity,
  Tags,
  RotateCcw,
} from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { Modal } from '../components/Modal'
import { Spinner } from '../components/Spinner'
import { TagsSection } from '../components/TagsSection'
import { useApiData } from '../hooks/useApiData'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { useAuthStore } from '../store/auth'
import {
  getFeedFreshness,
  getMe,
  resetReco,
} from '../api'

export const Profile = () => {
  const navigate = useNavigate()
  const storedEmail = useAuthStore((s) => s.email)
  const logout = useAuthStore((s) => s.logout)

  // Authoritative counts + email from the server (E7-S9). The auth store's
  // email is only a fallback while the request is in flight.
  const { data: me, loading, reload: reloadMe } = useApiData(getMe, [])
  const email = me?.email ?? storedEmail ?? 'user@example.com'

  // ── Reset recommendations (E17-S5) ───────────────────────────────────────
  const [confirmResetReco, setConfirmResetReco] = useState(false)
  const [resettingReco, setResettingReco] = useState(false)
  const [resetRecoDone, setResetRecoDone] = useState(false)

  const doResetReco = async () => {
    setResettingReco(true)
    try {
      await resetReco()
      setConfirmResetReco(false)
      setResetRecoDone(true)
      // Learned weights drove the keyword count shown on this screen.
      reloadMe()
    } catch {
      // Keep the modal open; the user can retry.
    } finally {
      setResettingReco(false)
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

          {/* Tags (E24-S8) — per-user tag lifecycle: rename, per-tag feed
              threshold (with inherit), delete. Attaching tags to sources
              happens on the Sources screen. Hidden while the user has no
              tags — creation is on-the-fly from Sources. */}
          {me && <TagsSection />}

          {/* Feed freshness (E19-S7, E19-S8) — a light "is new content on its
              way?" pill, shown to everyone. The detailed instance telemetry
              (pipeline health, OpenRouter bill, Run now) lives in the
              admin-only Administration › Monitoring section. */}
          {me && <FeedFreshnessRow />}

          {/* Reset recommendations (E17-S5) — destructive, gated behind a
              confirmation modal. Sits just above Sign out, grouped with the
              other irreversible action. */}
          <button
            onClick={() => {
              setResetRecoDone(false)
              setConfirmResetReco(true)
            }}
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
              <RotateCcw size={16} />
            </div>
            <span className="flex-1 text-left">
              {resetRecoDone ? 'Recommendations reset ✓' : 'Reset recommendations'}
            </span>
            <ChevronRight size={18} style={{ color: 'var(--text-tertiary)' }} />
          </button>

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

      {/* Reset-recommendations confirmation modal (E17-S5). */}
      {confirmResetReco && (
        <Modal
          onClose={() => !resettingReco && setConfirmResetReco(false)}
          ariaLabel="Reset recommendations"
        >
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              margin: '0 0 8px',
              color: 'var(--text-primary)',
            }}
          >
            Reset recommendations?
          </h3>
          <p
            style={{
              fontSize: 13,
              lineHeight: 1.5,
              color: 'var(--text-secondary)',
              margin: '0 0 16px',
            }}
          >
            This clears your likes and dislikes and the preferences learned
            from them, so your feed starts fresh. Your saved articles and
            pinned keywords are kept. This cannot be undone.
          </p>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setConfirmResetReco(false)}
              disabled={resettingReco}
              style={{
                padding: '8px 14px',
                borderRadius: 10,
                border: '1px solid var(--divider)',
                background: 'transparent',
                color: 'var(--text-secondary)',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={doResetReco}
              disabled={resettingReco}
              style={{
                padding: '8px 14px',
                borderRadius: 10,
                border: 'none',
                background: 'var(--action-dislike)',
                color: '#fff',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                opacity: resettingReco ? 0.7 : 1,
              }}
            >
              {resettingReco ? 'Resetting…' : 'Reset'}
            </button>
          </div>
        </Modal>
      )}

      <BottomNav />
    </div>
  )
}

// E19-S7 — feed-freshness pill, shown to every user (E19-S8). Self-contained:
// fetches its own lightweight /stats/freshness slice (no cost, no errors, no
// run trigger). Renders nothing until loaded, and on error, to avoid a noisy
// empty state.
const FeedFreshnessRow = () => {
  const { data, loading } = useApiData(getFeedFreshness, [])
  if (loading || !data) return null
  const fetching =
    data.pipeline_status === 'running' || data.pending_enrichment > 0
  return (
    <div
      className="glass-sm flex items-center gap-3 w-full"
      style={{
        borderRadius: 16,
        padding: '14px 16px',
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
        {fetching ? <Spinner size={14} /> : <Activity size={16} />}
      </div>
      <span className="flex-1 text-left">
        {fetching ? 'Nouveau contenu en route…' : 'Feed à jour'}
        {!fetching && data.last_completed_at && (
          <span
            style={{
              display: 'block',
              fontSize: 11,
              color: 'var(--text-tertiary)',
            }}
          >
            mis à jour {formatTimeAgo(data.last_completed_at)}
          </span>
        )}
      </span>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 999,
          background: fetching ? 'var(--accent)' : '#22c55e',
        }}
      />
    </div>
  )
}
