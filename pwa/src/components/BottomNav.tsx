import { useLocation, useNavigate } from 'react-router-dom'
import { LayoutGrid, Bookmark, SlidersHorizontal, User } from 'lucide-react'

const TABS = [
  { icon: LayoutGrid, route: '/', label: 'Feed' },
  { icon: Bookmark, route: '/saved', label: 'Saved' },
  { icon: SlidersHorizontal, route: '/keywords', label: 'Keywords' },
  { icon: User, route: '/profile', label: 'Profile' },
] as const

export const BottomNav = () => {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 flex justify-around items-center"
      style={{
        padding: '8px 20px calc(env(safe-area-inset-bottom, 0px) + 16px)',
        borderTop: '1px solid rgba(255, 255, 255, 0.05)',
        background: 'rgba(12, 16, 24, 0.85)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
      }}
    >
      {TABS.map(({ icon: Icon, route, label }) => {
        const active = location.pathname === route
        return (
          <button
            key={route}
            onClick={() => navigate(route)}
            aria-label={label}
            className="flex items-center justify-center transition-colors"
            style={{
              padding: '8px 14px',
              borderRadius: 20,
              color: active ? 'var(--accent)' : 'var(--text-tertiary)',
              background: active ? 'var(--accent-subtle)' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontSize: 22,
            }}
          >
            <Icon size={22} />
          </button>
        )
      })}
    </nav>
  )
}
