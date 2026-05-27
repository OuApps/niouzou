import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Feed } from './screens/Feed'
import { ArticleDetail } from './screens/ArticleDetail'
import { Saved } from './screens/Saved'
import { Keywords } from './screens/Keywords'
import { Profile } from './screens/Profile'
import { Sources } from './screens/Sources'
import { Login } from './screens/Login'
import { Register } from './screens/Register'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Feed />} />
        <Route path="/articles/:id" element={<ArticleDetail />} />
        <Route path="/saved" element={<Saved />} />
        <Route path="/keywords" element={<Keywords />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    </BrowserRouter>
  )
}
