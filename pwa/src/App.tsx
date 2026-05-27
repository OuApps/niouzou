import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import type { ReactElement } from 'react'
import { Feed } from './screens/Feed'
import { ArticleDetail } from './screens/ArticleDetail'
import { Saved } from './screens/Saved'
import { Keywords } from './screens/Keywords'
import { Profile } from './screens/Profile'
import { Sources } from './screens/Sources'
import { Login } from './screens/Login'
import { Register } from './screens/Register'
import { useAuthStore } from './store/auth'

/** Gate authenticated screens: bounce to /login when there is no token. */
function RequireAuth({ children }: { children: ReactElement }) {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: location }} />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RequireAuth><Feed /></RequireAuth>} />
        <Route path="/articles/:id" element={<RequireAuth><ArticleDetail /></RequireAuth>} />
        <Route path="/saved" element={<RequireAuth><Saved /></RequireAuth>} />
        <Route path="/keywords" element={<RequireAuth><Keywords /></RequireAuth>} />
        <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
        <Route path="/sources" element={<RequireAuth><Sources /></RequireAuth>} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    </BrowserRouter>
  )
}
