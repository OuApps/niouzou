import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { useAuthStore } from '../store/auth'
import { register, ApiError } from '../api'

export const Register = () => {
  const navigate = useNavigate()
  const sync = useAuthStore((s) => s.sync)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [errors, setErrors] = useState<{ email?: string; password?: string; confirm?: string; form?: string }>({})
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const newErrors: typeof errors = {}
    if (!email.trim()) newErrors.email = 'Email is required'
    if (!password.trim()) newErrors.password = 'Password is required'
    else if (password.length < 8) newErrors.password = 'Password must be at least 8 characters'
    if (password !== confirmPassword) newErrors.confirm = 'Passwords do not match'
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }
    setSubmitting(true)
    try {
      await register(email.trim(), password)
      sync()
      navigate('/', { replace: true })
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 409
          ? 'An account with this email already exists'
          : err instanceof ApiError
            ? err.message
            : 'Something went wrong. Please try again.'
      setErrors({ form: message })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col min-h-dvh relative">
      <BlobBackground />

      <div className="relative z-10 flex-1 flex flex-col items-center justify-center" style={{ padding: '0 24px' }}>
        <h1
          style={{
            fontSize: 28,
            fontWeight: 600,
            color: 'var(--accent)',
            marginBottom: 8,
          }}
        >
          niouzou
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 36 }}>
          Create your account
        </p>

        <form onSubmit={handleSubmit} className="w-full" style={{ maxWidth: 320 }}>
          <div style={{ marginBottom: 16 }}>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                setErrors((prev) => ({ ...prev, email: undefined, form: undefined }))
              }}
              style={{
                width: '100%',
                padding: '12px 14px',
                borderRadius: 12,
                border: errors.email ? '1px solid var(--action-dislike)' : '1px solid rgba(255,255,255,0.10)',
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-primary)',
                fontSize: 14,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            {errors.email && (
              <p style={{ fontSize: 11, color: 'var(--action-dislike)', marginTop: 4, paddingLeft: 2 }}>
                {errors.email}
              </p>
            )}
          </div>

          <div style={{ marginBottom: 16 }}>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                setErrors((prev) => ({ ...prev, password: undefined, form: undefined }))
              }}
              style={{
                width: '100%',
                padding: '12px 14px',
                borderRadius: 12,
                border: errors.password ? '1px solid var(--action-dislike)' : '1px solid rgba(255,255,255,0.10)',
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-primary)',
                fontSize: 14,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            {errors.password && (
              <p style={{ fontSize: 11, color: 'var(--action-dislike)', marginTop: 4, paddingLeft: 2 }}>
                {errors.password}
              </p>
            )}
          </div>

          <div style={{ marginBottom: 24 }}>
            <input
              type="password"
              placeholder="Confirm password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value)
                setErrors((prev) => ({ ...prev, confirm: undefined, form: undefined }))
              }}
              style={{
                width: '100%',
                padding: '12px 14px',
                borderRadius: 12,
                border: errors.confirm ? '1px solid var(--action-dislike)' : '1px solid rgba(255,255,255,0.10)',
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-primary)',
                fontSize: 14,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            {errors.confirm && (
              <p style={{ fontSize: 11, color: 'var(--action-dislike)', marginTop: 4, paddingLeft: 2 }}>
                {errors.confirm}
              </p>
            )}
          </div>

          {errors.form && (
            <p
              style={{
                fontSize: 12,
                color: 'var(--action-dislike)',
                marginBottom: 12,
                textAlign: 'center',
              }}
            >
              {errors.form}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            style={{
              width: '100%',
              padding: '14px 0',
              borderRadius: 12,
              background: 'var(--accent)',
              color: '#0c1018',
              border: 'none',
              fontSize: 14,
              fontWeight: 600,
              cursor: submitting ? 'default' : 'pointer',
              opacity: submitting ? 0.6 : 1,
              marginBottom: 16,
            }}
          >
            {submitting ? 'Creating account…' : 'Create account'}
          </button>

          <p className="text-center" style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: 'var(--accent)', textDecoration: 'none' }}>
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
