import { useNavigate } from 'react-router-dom'
import { Rss, LogOut, ChevronRight } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { useAuthStore } from '../store/auth'

export const Profile = () => {
  const navigate = useNavigate()
  const email = useAuthStore((s) => s.email) ?? 'user@example.com'
  const logout = useAuthStore((s) => s.logout)

  const initials = email
    .split('@')[0]
    .slice(0, 2)
    .toUpperCase()

  const stats = [
    { label: 'Read', value: 142 },
    { label: 'Liked', value: 67 },
    { label: 'Sources', value: 4 },
  ]

  const handleSignOut = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex flex-col min-h-dvh relative">
      <BlobBackground />

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
          {stats.map((s) => (
            <div
              key={s.label}
              className="glass-sm flex-1 flex flex-col items-center"
              style={{ borderRadius: 16, padding: '14px 8px' }}
            >
              <span style={{ fontSize: 18, fontWeight: 600, marginBottom: 2 }}>{s.value}</span>
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
      </div>

      <BottomNav />
    </div>
  )
}
