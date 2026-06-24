import { useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowLeft, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { Modal } from '../components/Modal'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { useApiData } from '../hooks/useApiData'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import {
  getAdminConfig,
  patchAdminConfig,
  getAdminModels,
  getAdminUsers,
  getAdminPrompts,
  getStats,
  resetUserPassword,
  deleteAdminUser,
  updateAdminPrompt,
  compactKeywordsPreview,
  compactKeywordsGet,
  compactKeywordsApply,
  compactKeywordsReject,
  ApiError,
  type AdminConfig,
  type AdminModel,
  type AdminUser,
  type CompactionGroup,
  type CompactionPreview,
  type LlmPrompt,
} from '../api'
import { useAuthStore } from '../store/auth'

export const Admin = () => {
  const navigate = useNavigate()
  const { data: config, loading: configLoading, error: configError, reload: reloadConfig } = useApiData(
    getAdminConfig,
    [],
  )
  const { data: models } = useApiData(getAdminModels, [])
  const { data: users, loading: usersLoading, error: usersError, reload: reloadUsers } = useApiData(
    () => getAdminUsers(),
    [],
  )

  // E10-S3 — Keyword compaction stats; refreshed after apply/reject.
  const {
    data: stats,
    reload: reloadStats,
  } = useApiData(getStats, [])

  return (
    <div className="flex flex-col h-dvh overflow-y-auto relative">
      <BlobBackground />

      <header className="relative z-10 flex items-center" style={{ padding: '16px 16px 8px' }}>
        <button
          onClick={() => navigate(-1)}
          aria-label="Back"
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-primary)',
            cursor: 'pointer',
            padding: 4,
          }}
        >
          <ArrowLeft size={20} />
        </button>
        <h1
          className="flex-1 text-center"
          style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)', marginRight: 28 }}
        >
          Administration
        </h1>
      </header>

      {/* No flex-1 here: a flex-basis:0% child inside a column flex container
          can short-circuit the parent's intrinsic height calculation, leaving
          the long Users list unscrollable on iOS. The wrapper already owns
          ``overflow-y-auto h-dvh`` so a normal block grows naturally.

          E19-S2 — every section is a collapsible AdminSection, closed by
          default, for a consistent accordion instead of the old mix of
          always-open headers and ad-hoc toggles. */}
      <div className="relative z-10" style={{ padding: '16px 16px 40px' }}>
        <AdminSection title="Configuration">
          {configLoading ? (
            <div className="flex justify-center" style={{ paddingTop: 20 }}>
              <Spinner size={24} />
            </div>
          ) : configError ? (
            <ErrorState message={configError} onRetry={reloadConfig} />
          ) : config ? (
            <div className="flex flex-col gap-2">
              <ConfigRow
                label="OpenRouter API Key"
                config={config}
                field="openrouter_api_key"
                type="password"
                onSave={reloadConfig}
              />
              <ConfigRow
                label="OpenRouter Model"
                config={config}
                field="openrouter_model"
                type="model"
                models={models ?? []}
                onSave={reloadConfig}
              />
              <ConfigRow
                label="Fetch Interval (minutes)"
                config={config}
                field="cron_fetch_interval"
                type="number"
                min={1}
                max={1440}
                onSave={reloadConfig}
              />
              <ConfigRow
                label="Nightly Refresh (hour)"
                config={config}
                field="cron_nightly_refresh_hour"
                type="number"
                min={0}
                max={23}
                onSave={reloadConfig}
              />
              <ConfigRow
                label="Score threshold (%)"
                config={config}
                field="score_threshold"
                type="percent"
                min={0}
                max={100}
                onSave={reloadConfig}
              />
            </div>
          ) : null}
        </AdminSection>

        {/* Scoring engine section (E16-S4) */}
        {config ? (
          <AdminSection title="Scoring engine">
            <ScoringEngineSection config={config} onChange={reloadConfig} />
          </AdminSection>
        ) : null}

        {/* Keywords section (E10-S3) */}
        <AdminSection title="Keywords">
          <KeywordsSection stats={stats} onChange={reloadStats} />
        </AdminSection>

        {/* Users section */}
        <AdminSection title="Users">
          {usersLoading ? (
            <div className="flex justify-center" style={{ paddingTop: 20 }}>
              <Spinner size={24} />
            </div>
          ) : usersError ? (
            <ErrorState message={usersError} onRetry={reloadUsers} />
          ) : users && users.length > 0 ? (
            <div className="flex flex-col gap-2">
              {users.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  onPasswordReset={reloadUsers}
                  onDelete={reloadUsers}
                />
              ))}
            </div>
          ) : null}
        </AdminSection>

        {/* E13-S2 — LLM prompts editor */}
        <AdminSection title="LLM Prompts">
          <PromptsSection />
        </AdminSection>
      </div>
    </div>
  )
}

interface AdminSectionProps {
  title: string
  defaultOpen?: boolean
  children: ReactNode
}

/**
 * E19-S2 — uniform collapsible section for the admin screen. Closed by
 * default; children mount only when open (so a section's data fetch stays
 * lazy where the content owns its own fetch).
 */
const AdminSection = ({ title, defaultOpen = false, children }: AdminSectionProps) => {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{ marginBottom: 24 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          fontSize: 14,
          fontWeight: 600,
          color: 'var(--text-secondary)',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          padding: '0 0 12px 0',
          marginBottom: open ? 12 : 0,
        }}
      >
        <span>{title}</span>
        {open ? (
          <ChevronUp size={16} style={{ color: 'var(--text-tertiary)' }} />
        ) : (
          <ChevronDown size={16} style={{ color: 'var(--text-tertiary)' }} />
        )}
      </button>
      {open && children}
    </div>
  )
}

interface ConfigRowProps {
  label: string
  config: AdminConfig
  field: keyof AdminConfig
  // ``percent`` stores 0-1 server-side but edits/displays 0-100 % — used by
  // ``score_threshold`` so the admin types a number that matches what the
  // score badge shows on the feed.
  type: 'text' | 'password' | 'number' | 'float' | 'percent' | 'model'
  models?: AdminModel[]
  min?: number
  max?: number
  onSave: () => void
}

const ConfigRow = ({ label, config, field, type, models = [], min, max, onSave }: ConfigRowProps) => {
  // For percent fields the raw stored value is 0-1; the editor speaks 0-100.
  const initial = config[field]
  const editValue =
    type === 'percent' && typeof initial === 'number'
      ? String(Math.round(initial * 100))
      : String(initial ?? '')
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(editValue)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isNumeric = type === 'number' || type === 'float' || type === 'percent'

  const handleSave = async () => {
    setError(null)
    setSaving(true)
    try {
      const patch: Record<string, string | number> = {}
      if (isNumeric) {
        const raw =
          type === 'number' ? parseInt(value, 10) : parseFloat(value)
        if (isNaN(raw)) {
          setError('Invalid number')
          setSaving(false)
          return
        }
        if (min !== undefined && raw < min) {
          setError(`Must be at least ${min}`)
          setSaving(false)
          return
        }
        if (max !== undefined && raw > max) {
          setError(`Must be at most ${max}`)
          setSaving(false)
          return
        }
        // Percent → store as 0-1 float on the backend.
        patch[field] = type === 'percent' ? raw / 100 : raw
      } else {
        patch[field] = value
      }
      await patchAdminConfig(patch as any)
      setEditing(false)
      onSave()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const displayValue =
    type === 'password' && value
      ? `${value.slice(0, 5)}***${value.slice(-4)}`
      : type === 'model'
        ? models.find((m) => m.id === value)?.name ?? value
        : type === 'percent'
          ? `${value}%`
          : value

  return (
    <div className="glass-sm flex flex-col" style={{ borderRadius: 16, padding: '12px 14px' }}>
      <div className="flex items-center justify-between">
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</span>
        {!editing ? (
          <button
            onClick={() => setEditing(true)}
            style={{
              fontSize: 11,
              color: 'var(--accent-text)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
              fontWeight: 600,
            }}
          >
            Edit
          </button>
        ) : null}
      </div>

      {editing ? (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {type === 'model' ? (
            <select
              value={value}
              onChange={(e) => setValue(e.target.value)}
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.10)',
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-primary)',
                fontSize: 12,
              }}
            >
              <option value="">Select a model</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} — ${m.input_price_per_m.toFixed(2)} in / ${m.output_price_per_m.toFixed(2)} out per M tokens
                </option>
              ))}
            </select>
          ) : (
            <input
              type={
                type === 'password'
                  ? 'password'
                  : isNumeric
                    ? 'number'
                    : 'text'
              }
              step={type === 'float' ? 0.05 : type === 'percent' ? 1 : undefined}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={label}
              min={isNumeric ? min : undefined}
              max={isNumeric ? max : undefined}
              style={{
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.10)',
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-primary)',
                fontSize: 12,
              }}
            />
          )}
          {error && <p style={{ fontSize: 10, color: 'var(--action-dislike)' }}>{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                flex: 1,
                padding: '6px 10px',
                borderRadius: 8,
                background: 'var(--accent)',
                color: '#0c1018',
                border: 'none',
                fontSize: 11,
                fontWeight: 600,
                cursor: saving ? 'default' : 'pointer',
                opacity: saving ? 0.6 : 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 4,
              }}
            >
              {saving && <Spinner size={10} />}
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              onClick={() => {
                setEditing(false)
                setError(null)
                setValue(String(config[field] ?? ''))
              }}
              disabled={saving}
              style={{
                flex: 1,
                padding: '6px 10px',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.08)',
                color: 'var(--text-primary)',
                border: '1px solid rgba(255,255,255,0.10)',
                fontSize: 11,
                fontWeight: 600,
                cursor: saving ? 'default' : 'pointer',
                opacity: saving ? 0.6 : 1,
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <p style={{ fontSize: 12, color: 'var(--text-primary)', marginTop: 4 }}>{displayValue || '—'}</p>
      )}
    </div>
  )
}

// ── E16-S4 — Scoring engine toggle ────────────────────────────────────────────

interface ScoringEngineSectionProps {
  config: AdminConfig
  onChange: () => void
}

const SCORING_ENGINES = [
  {
    id: 'keyword' as const,
    label: 'Keyword',
    subtitle: 'AI keywords × learned weights',
  },
  {
    id: 'smart' as const,
    label: 'Smart Match',
    subtitle: 'Semantic similarity to your liked articles',
  },
]

const ScoringEngineSection = ({ config, onChange }: ScoringEngineSectionProps) => {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const select = async (mode: 'keyword' | 'smart') => {
    if (mode === config.scoring_mode || saving) return
    setError(null)
    setSaving(true)
    try {
      await patchAdminConfig({ scoring_mode: mode })
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const pct =
    config.articles_total > 0
      ? Math.round((config.embeddings_done / config.articles_total) * 100)
      : 0

  return (
    <div
      className="glass-sm flex flex-col"
      style={{ borderRadius: 16, padding: '12px 14px', gap: 10 }}
    >
      {SCORING_ENGINES.map((engine) => (
        <label
          key={engine.id}
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
            cursor: saving ? 'default' : 'pointer',
            opacity: saving ? 0.6 : 1,
          }}
        >
          <input
            type="radio"
            name="scoring_mode"
            checked={config.scoring_mode === engine.id}
            onChange={() => select(engine.id)}
            disabled={saving}
            style={{ marginTop: 3, accentColor: 'var(--accent-text)' }}
          />
          <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {engine.label}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              {engine.subtitle}
            </span>
          </span>
        </label>
      ))}

      <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
        Embeddings: {config.embeddings_done.toLocaleString()} /{' '}
        {config.articles_total.toLocaleString()} articles ({pct}%)
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
        Both scores are always computed; this only selects which one filters
        and ranks the feed. Switching is instant — no rescore needed.
      </div>
      {error && (
        <p style={{ fontSize: 11, color: 'var(--action-dislike)' }}>{error}</p>
      )}
    </div>
  )
}

interface UserRowProps {
  user: AdminUser
  onPasswordReset: () => void
  onDelete: () => void
}

const UserRow = ({ user, onPasswordReset, onDelete }: UserRowProps) => {
  const currentEmail = useAuthStore((s) => s.email)
  const isSelf = currentEmail?.toLowerCase() === user.email.toLowerCase()
  const [resettingPassword, setResettingPassword] = useState(false)
  const [showPasswordForm, setShowPasswordForm] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [confirmEmail, setConfirmEmail] = useState<string | null>(null) // null = modal closed
  const [confirmInput, setConfirmInput] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const handleResetPassword = async () => {
    setPasswordError(null)
    if (!newPassword.trim()) {
      setPasswordError('Password cannot be empty')
      return
    }
    setResettingPassword(true)
    try {
      await resetUserPassword(user.id, newPassword)
      setShowPasswordForm(false)
      setNewPassword('')
      onPasswordReset()
    } catch (err) {
      setPasswordError(err instanceof ApiError ? err.message : 'Reset failed')
    } finally {
      setResettingPassword(false)
    }
  }

  const handleConfirmDelete = async () => {
    setDeleteError(null)
    setDeleting(true)
    try {
      await deleteAdminUser(user.id)
      setConfirmEmail(null)
      onDelete()
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="glass-sm flex flex-col" style={{ borderRadius: 16, padding: '12px 14px' }}>
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <p style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{user.email}</p>
          <div className="flex items-center gap-2">
            {user.is_admin && (
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  color: 'var(--accent-text)',
                  background: 'var(--accent-subtle)',
                  padding: '2px 6px',
                  borderRadius: 4,
                }}
              >
                Admin
              </span>
            )}
            <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
              {new Date(user.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
        {!showPasswordForm && (
          <div className="flex items-center gap-3" style={{ flexShrink: 0 }}>
            <button
              onClick={() => setShowPasswordForm(true)}
              style={{
                fontSize: 11,
                color: 'var(--accent-text)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
                fontWeight: 600,
              }}
            >
              Reset Password
            </button>
            {!isSelf && (
              <button
                onClick={() => {
                  setConfirmInput('')
                  setDeleteError(null)
                  setConfirmEmail(user.email)
                }}
                style={{
                  fontSize: 11,
                  color: 'var(--action-dislike)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                  fontWeight: 600,
                }}
              >
                Delete
              </button>
            )}
          </div>
        )}
      </div>

      {confirmEmail !== null && (
        <DeleteUserModal
          email={confirmEmail}
          confirmInput={confirmInput}
          setConfirmInput={setConfirmInput}
          deleting={deleting}
          error={deleteError}
          onCancel={() => setConfirmEmail(null)}
          onConfirm={handleConfirmDelete}
        />
      )}

      {showPasswordForm && !confirmEmail && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password"
            style={{
              padding: '8px 10px',
              borderRadius: 8,
              border: '1px solid rgba(255,255,255,0.10)',
              background: 'rgba(255,255,255,0.04)',
              color: 'var(--text-primary)',
              fontSize: 12,
            }}
          />
          {passwordError && (
            <div className="flex items-start gap-2" style={{ padding: '8px 10px', background: 'rgba(248, 113, 113, 0.10)', borderRadius: 8 }}>
              <AlertTriangle size={12} style={{ color: 'var(--action-dislike)', flexShrink: 0, marginTop: 2 }} />
              <p style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{passwordError}</p>
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleResetPassword}
              disabled={resettingPassword}
              style={{
                flex: 1,
                padding: '6px 10px',
                borderRadius: 8,
                background: 'var(--accent)',
                color: '#0c1018',
                border: 'none',
                fontSize: 11,
                fontWeight: 600,
                cursor: resettingPassword ? 'default' : 'pointer',
                opacity: resettingPassword ? 0.6 : 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 4,
              }}
            >
              {resettingPassword && <Spinner size={10} />}
              {resettingPassword ? 'Resetting…' : 'Reset'}
            </button>
            <button
              onClick={() => {
                setShowPasswordForm(false)
                setNewPassword('')
                setPasswordError(null)
              }}
              disabled={resettingPassword}
              style={{
                flex: 1,
                padding: '6px 10px',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.08)',
                color: 'var(--text-primary)',
                border: '1px solid rgba(255,255,255,0.10)',
                fontSize: 11,
                fontWeight: 600,
                cursor: resettingPassword ? 'default' : 'pointer',
                opacity: resettingPassword ? 0.6 : 1,
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

interface DeleteUserModalProps {
  email: string
  confirmInput: string
  setConfirmInput: (v: string) => void
  deleting: boolean
  error: string | null
  onCancel: () => void
  onConfirm: () => void
}

const DeleteUserModal = ({
  email,
  confirmInput,
  setConfirmInput,
  deleting,
  error,
  onCancel,
  onConfirm,
}: DeleteUserModalProps) => {
  const matches = confirmInput === email
  return (
    <Modal
      onClose={() => !deleting && onCancel()}
      maxWidth={320}
      ariaLabel="Delete user"
    >
      <h3
        style={{
          fontSize: 16,
          fontWeight: 600,
          margin: '0 0 8px',
          color: 'var(--text-primary)',
        }}
      >
        Delete user?
      </h3>
      <p
        style={{
          fontSize: 13,
          lineHeight: 1.5,
          color: 'var(--text-secondary)',
          margin: '0 0 12px',
        }}
      >
        This wipes <strong>{email}</strong> and every related row (sources,
        articles seen, feedback, weights). This cannot be undone.
      </p>
      <input
        type="text"
        value={confirmInput}
        onChange={(e) => setConfirmInput(e.target.value)}
        placeholder="Type the email to confirm"
        autoFocus
        style={{
          width: '100%',
          padding: '8px 12px',
          borderRadius: 10,
          border: '1px solid var(--divider)',
          background: 'rgba(255,255,255,0.04)',
          color: 'var(--text-primary)',
          fontSize: 13,
          marginBottom: error ? 8 : 16,
        }}
      />
      {error && (
        <p style={{ fontSize: 12, color: 'var(--action-dislike)', margin: '0 0 16px' }}>
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button
          onClick={onCancel}
          disabled={deleting}
          style={{
            padding: '8px 14px',
            borderRadius: 10,
            border: '1px solid var(--divider)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            fontSize: 13,
            fontWeight: 600,
            cursor: deleting ? 'default' : 'pointer',
          }}
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={!matches || deleting}
          style={{
            padding: '8px 14px',
            borderRadius: 10,
            border: 'none',
            background: matches ? 'var(--action-dislike)' : 'rgba(255,255,255,0.08)',
            color: matches ? '#fff' : 'var(--text-tertiary)',
            fontSize: 13,
            fontWeight: 600,
            cursor: !matches || deleting ? 'default' : 'pointer',
            opacity: deleting ? 0.7 : 1,
          }}
        >
          {deleting ? 'Deleting…' : 'Delete'}
        </button>
      </div>
    </Modal>
  )
}


// ── E13-S2 — LLM prompts editor ────────────────────────────────────────────

const PromptsSection = () => {
  // E19-S2 — collapse chrome now lives in the parent AdminSection; this is
  // pure content (fetch fires when the section is first opened).
  const { data: prompts, loading, error, reload } = useApiData(getAdminPrompts, [])

  if (loading) {
    return (
      <div className="flex justify-center" style={{ paddingTop: 20 }}>
        <Spinner size={24} />
      </div>
    )
  }
  if (error) {
    return <ErrorState message={error} onRetry={reload} />
  }
  if (prompts && prompts.length > 0) {
    return (
      <div className="flex flex-col gap-3">
        {prompts.map((p) => (
          <PromptCard key={p.name} prompt={p} onSaved={reload} />
        ))}
      </div>
    )
  }
  return null
}

interface PromptCardProps {
  prompt: LlmPrompt
  onSaved: () => void
}

const PromptCard = ({ prompt, onSaved }: PromptCardProps) => {
  const [draft, setDraft] = useState(prompt.body)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dirty = draft !== prompt.body

  const handleSave = async () => {
    setError(null)
    setSaving(true)
    try {
      await updateAdminPrompt(prompt.name, draft)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(draft)
    } catch {
      // Clipboard API not available — silent no-op.
    }
  }

  return (
    <div className="glass-sm" style={{ borderRadius: 16, padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="flex items-center justify-between">
        <code style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)' }}>{prompt.name}</code>
        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
          {formatTimeAgo(prompt.updated_at)}
        </span>
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={12}
        spellCheck={false}
        style={{
          width: '100%',
          padding: '10px 12px',
          borderRadius: 10,
          border: '1px solid rgba(255,255,255,0.10)',
          background: 'rgba(0,0,0,0.20)',
          color: 'var(--text-primary)',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          fontSize: 11,
          lineHeight: 1.5,
          resize: 'vertical',
          outline: 'none',
        }}
      />
      {error && (
        <p style={{ fontSize: 11, color: 'var(--action-dislike)' }}>{error}</p>
      )}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          style={{
            padding: '6px 12px',
            borderRadius: 8,
            background: dirty ? 'var(--accent)' : 'rgba(255,255,255,0.08)',
            color: dirty ? '#0c1018' : 'var(--text-tertiary)',
            border: 'none',
            fontSize: 11,
            fontWeight: 600,
            cursor: !dirty || saving ? 'default' : 'pointer',
            opacity: saving ? 0.6 : 1,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          {saving && <Spinner size={10} />}
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={handleCopy}
          style={{
            padding: '6px 12px',
            borderRadius: 8,
            background: 'rgba(255,255,255,0.08)',
            color: 'var(--text-primary)',
            border: '1px solid rgba(255,255,255,0.10)',
            fontSize: 11,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Copy
        </button>
      </div>
    </div>
  )
}


// ── E10-S3 — Keyword compaction admin panel ─────────────────────────────────

interface KeywordsSectionProps {
  stats:
    | {
        keywords: {
          distinct_keyword_count: number
          last_compact_at: string | null
          pending_compaction_id: string | null
        }
      }
    | null
  onChange: () => void
}

const KeywordsSection = ({ stats, onChange }: KeywordsSectionProps) => {
  const [preview, setPreview] = useState<CompactionPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)

  const runPreview = async () => {
    setError(null)
    setLoading(true)
    try {
      const p = await compactKeywordsPreview()
      setPreview(p)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Preview failed')
    } finally {
      setLoading(false)
    }
  }

  const resumePending = async () => {
    const pendingId = stats?.keywords.pending_compaction_id
    if (!pendingId) return
    setError(null)
    setLoading(true)
    try {
      const p = await compactKeywordsGet(pendingId)
      setPreview(p)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Race window: the preview was rejected/applied from another tab
        // between our stats read and this fetch. Refresh stats so the
        // "Resume" button disappears.
        onChange()
        setError('This analysis is no longer available.')
      } else {
        setError(err instanceof ApiError ? err.message : 'Resume failed')
      }
    } finally {
      setLoading(false)
    }
  }

  const apply = async () => {
    if (!preview) return
    setApplying(true)
    try {
      await compactKeywordsApply(preview.id)
      setPreview(null)
      // Stats reflect the new vocab size + last_compact_at after a moment.
      setTimeout(onChange, 10_000)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  const reject = async () => {
    if (!preview) return
    try {
      await compactKeywordsReject(preview.id)
    } catch {
      // Best effort — closing the modal is enough.
    }
    setPreview(null)
    onChange()
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        className="glass-sm flex items-center justify-between"
        style={{ borderRadius: 16, padding: '12px 14px' }}
      >
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Distinct keywords
          </div>
          <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>
            {stats?.keywords.distinct_keyword_count ?? '—'}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Last compaction
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            {stats?.keywords.last_compact_at
              ? formatTimeAgo(stats.keywords.last_compact_at)
              : 'never'}
          </div>
        </div>
      </div>

      <button
        onClick={runPreview}
        disabled={loading || applying}
        style={{
          padding: '10px 14px',
          borderRadius: 12,
          border: '1px solid rgba(255,255,255,0.10)',
          background: 'var(--accent)',
          color: '#0c1018',
          fontSize: 13,
          fontWeight: 600,
          cursor: loading || applying ? 'not-allowed' : 'pointer',
          opacity: loading || applying ? 0.6 : 1,
        }}
      >
        {loading ? 'Analysing…' : 'Analyse compaction'}
      </button>

      {stats?.keywords.pending_compaction_id && !preview && (
        <button
          onClick={resumePending}
          style={{
            padding: '8px 12px',
            borderRadius: 10,
            border: '1px solid rgba(255,255,255,0.10)',
            background: 'transparent',
            color: 'var(--text-secondary)',
            fontSize: 12,
            cursor: 'pointer',
          }}
        >
          Resume previous analysis
        </button>
      )}

      {error && (
        <div
          style={{
            padding: '8px 12px',
            borderRadius: 10,
            background: 'rgba(248,113,113,0.10)',
            color: 'var(--action-dislike)',
            fontSize: 12,
          }}
        >
          {error}
        </div>
      )}

      {preview && (
        <CompactionPreviewModal
          preview={preview}
          onApply={apply}
          onReject={reject}
          applying={applying}
        />
      )}
    </div>
  )
}


interface PreviewModalProps {
  preview: CompactionPreview
  onApply: () => void
  onReject: () => void
  applying: boolean
}

const CompactionPreviewModal = ({
  preview,
  onApply,
  onReject,
  applying,
}: PreviewModalProps) => (
  <Modal onClose={onReject} maxWidth={560} ariaLabel="Keyword compaction preview">
    <div
      style={{
        fontSize: 16,
        fontWeight: 600,
        color: 'var(--text-primary)',
        marginBottom: 14,
      }}
    >
      {preview.groups.length === 0
        ? 'No groups to merge'
        : `${preview.groups.length} group(s) to merge`}
    </div>

    {preview.groups.length > 0 && (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          marginBottom: 18,
        }}
      >
        {preview.groups.map((g, idx) => (
          <CompactionGroupRow key={`${g.canonical}-${idx}`} group={g} />
        ))}
      </div>
    )}

    <div style={{ display: 'flex', gap: 10 }}>
      <button
        onClick={onApply}
        disabled={applying || preview.groups.length === 0}
        style={{
          flex: 1,
          padding: '10px 14px',
          borderRadius: 12,
          border: 'none',
          background: 'var(--accent)',
          color: '#0c1018',
          fontSize: 13,
          fontWeight: 600,
          cursor:
            applying || preview.groups.length === 0 ? 'not-allowed' : 'pointer',
          opacity: applying || preview.groups.length === 0 ? 0.6 : 1,
        }}
      >
        {applying ? 'Running…' : 'Apply'}
      </button>
      <button
        onClick={onReject}
        style={{
          flex: 1,
          padding: '10px 14px',
          borderRadius: 12,
          border: '1px solid rgba(255,255,255,0.10)',
          background: 'transparent',
          color: 'var(--text-secondary)',
          fontSize: 13,
          cursor: 'pointer',
        }}
      >
        Cancel
      </button>
    </div>
  </Modal>
)


const CompactionGroupRow = ({ group }: { group: CompactionGroup }) => {
  const pinned = group.skipped_reason === 'pinned'
  return (
    <div
      style={{
        padding: '10px 12px',
        borderRadius: 12,
        background: 'rgba(255,255,255,0.04)',
        opacity: pinned ? 0.5 : 1,
      }}
    >
      <div
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--text-primary)',
          marginBottom: 4,
        }}
      >
        {group.canonical}
        {pinned && (
          <span
            style={{
              marginLeft: 8,
              fontSize: 10,
              fontWeight: 400,
              color: 'var(--text-tertiary)',
            }}
          >
            (pinned — skipped)
          </span>
        )}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
        {group.aliases.join(', ')}
      </div>
    </div>
  )
}
