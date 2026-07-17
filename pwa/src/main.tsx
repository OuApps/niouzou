import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// Anti-Railway redirect (edge alignment). The PWA is served only from its
// canonical Cloudflare domain. If someone lands on the raw Railway origin
// (*.up.railway.app) — a stale link, a bookmarked internal URL — bounce them to
// the canonical host before the app mounts, preserving path/query/hash.
// Hardcoded and unconditional on purpose: the host is a runtime value (so Vite
// can't fold the branch away), and the redirect only ever fires on Railway's
// niouzou-specific origin — inert for local dev and self-hosting.
if (location.hostname.endsWith('.up.railway.app')) {
  location.replace(
    'https://niouzou.galaxou.com' +
      location.pathname +
      location.search +
      location.hash,
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
