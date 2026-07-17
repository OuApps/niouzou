import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// Anti-Railway redirect (edge alignment). The PWA is served only from its
// canonical Cloudflare domain (VITE_CANONICAL_URL, e.g.
// https://niouzou.galaxou.com). If someone lands on the raw Railway origin
// (*.up.railway.app) — a stale link, a bookmarked internal URL — bounce them
// to the canonical host before the app mounts, preserving path/query/hash.
// No-op when the canonical URL is unset (local dev, self-hosting).
const canonical = import.meta.env.VITE_CANONICAL_URL as string | undefined
if (canonical && window.location.hostname.endsWith('.up.railway.app')) {
  window.location.replace(
    canonical.replace(/\/$/, '') +
      window.location.pathname +
      window.location.search +
      window.location.hash,
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
