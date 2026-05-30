import { useState } from 'react'
import { ArrowLeft, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { useApiData } from '../hooks/useApiData'
import {
  getAdminConfig,
  patchAdminConfig,
  getAdminModels,
  getAdminUsers,
  resetUserPassword,
  ApiError,
  type AdminConfig,
  type AdminModel,
  type AdminUser,
} from '../api'

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

  const [usersOpen, setUsersOpen] = useState(false)

  return (
    <div className="flex flex-col min-h-dvh relative">
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

      <div className="relative z-10 flex-1" style={{ padding: '16px 16px 90px' }}>
        {/* Config section */}
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>
            Configuration
          </h2>

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
                label="Refresh Weights (hour)"
                config={config}
                field="cron_refresh_weights_hour"
                type="number"
                min={0}
                max={23}
                onSave={reloadConfig}
              />
            </div>
          ) : null}
        </div>

        {/* Users section */}
        <div>
          <button
            onClick={() => setUsersOpen((o) => !o)}
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
              marginBottom: 12,
            }}
            aria-expanded={usersOpen}
          >
            <span>Users</span>
            {usersOpen ? (
              <ChevronUp size={16} style={{ color: 'var(--text-tertiary)' }} />
            ) : (
              <ChevronDown size={16} style={{ color: 'var(--text-tertiary)' }} />
            )}
          </button>

          {usersOpen && (
            <>
              {usersLoading ? (
                <div className="flex justify-center" style={{ paddingTop: 20 }}>
                  <Spinner size={24} />
                </div>
              ) : usersError ? (
                <ErrorState message={usersError} onRetry={reloadUsers} />
              ) : users && users.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {users.map((user) => (
                    <UserRow key={user.id} user={user} onPasswordReset={reloadUsers} />
                  ))}
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

interface ConfigRowProps {
  label: string
  config: AdminConfig
  field: keyof AdminConfig
  type: 'text' | 'password' | 'number' | 'model'
  models?: AdminModel[]
  min?: number
  max?: number
  onSave: () => void
}

const ConfigRow = ({ label, config, field, type, models = [], min, max, onSave }: ConfigRowProps) => {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(String(config[field] ?? ''))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    setError(null)
    setSaving(true)
    try {
      const patch: Record<string, string | number> = {}
      if (type === 'number') {
        const num = parseInt(value, 10)
        if (isNaN(num)) {
          setError('Invalid number')
          setSaving(false)
          return
        }
        if (min !== undefined && num < min) {
          setError(`Must be at least ${min}`)
          setSaving(false)
          return
        }
        if (max !== undefined && num > max) {
          setError(`Must be at most ${max}`)
          setSaving(false)
          return
        }
        patch[field] = num
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
                  {m.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={type === 'password' ? 'password' : type === 'number' ? 'number' : 'text'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={label}
              min={type === 'number' ? min : undefined}
              max={type === 'number' ? max : undefined}
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

interface UserRowProps {
  user: AdminUser
  onPasswordReset: () => void
}

const UserRow = ({ user, onPasswordReset }: UserRowProps) => {
  const [resettingPassword, setResettingPassword] = useState(false)
  const [showPasswordForm, setShowPasswordForm] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)

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
        )}
      </div>

      {showPasswordForm && (
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
