import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { useAuthStore } from '../store/auth'

export const Login = () => {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({})

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const newErrors: typeof errors = {}
    if (!email.trim()) newErrors.email = 'Email is required'
    if (!password.trim()) newErrors.password = 'Password is required'
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }
    setAuth('fake-jwt-token-' + Date.now(), email)
    navigate('/')
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
          Sign in to your account
        </p>

        <form onSubmit={handleSubmit} className="w-full" style={{ maxWidth: 320 }}>
          <div style={{ marginBottom: 16 }}>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                setErrors((prev) => ({ ...prev, email: undefined }))
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

          <div style={{ marginBottom: 24 }}>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                setErrors((prev) => ({ ...prev, password: undefined }))
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

          <button
            type="submit"
            style={{
              width: '100%',
              padding: '14px 0',
              borderRadius: 12,
              background: 'var(--accent)',
              color: '#0c1018',
              border: 'none',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              marginBottom: 16,
            }}
          >
            Sign in
          </button>

          <p className="text-center" style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Don&apos;t have an account?{' '}
            <Link to="/register" style={{ color: 'var(--accent)', textDecoration: 'none' }}>
              Sign up
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
