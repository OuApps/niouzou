// Core HTTP layer for the Niouzou API (docs/API_SPEC.md).
//
// Responsibilities:
//  - Attach the JWT access token to every request (interceptor-style).
//  - On 401, transparently refresh the access token once and retry; if the
//    refresh fails, clear the session and bounce to /login.
//  - Surface the API's `{ error, message }` envelope as a typed ApiError so
//    screens can show friendly inline messages instead of raw JSON.

const BASE_URL: string = (() => {
  const url = import.meta.env.VITE_API_URL as string | undefined
  if (!url) {
    if (import.meta.env.PROD) {
      console.warn(
        '[niouzou] VITE_API_URL is not set — falling back to http://localhost:8000/api/v1. ' +
        'This is likely a misconfiguration in production.',
      )
    }
    return 'http://localhost:8000/api/v1'
  }
  return url
})()

const ACCESS_KEY = 'niouzou_token'
const REFRESH_KEY = 'niouzou_refresh'
const EMAIL_KEY = 'niouzou_email'

// ── Token storage (single source of truth: localStorage) ──────────────────

export const tokens = {
  access: () => localStorage.getItem(ACCESS_KEY),
  refresh: () => localStorage.getItem(REFRESH_KEY),
  email: () => localStorage.getItem(EMAIL_KEY),
  set: (access: string, refresh: string, email: string) => {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
    localStorage.setItem(EMAIL_KEY, email)
  },
  setAccess: (access: string) => localStorage.setItem(ACCESS_KEY, access),
  clear: () => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(EMAIL_KEY)
  },
}

// ── Error type ─────────────────────────────────────────────────────────────

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** A network-level failure (server unreachable, DNS, CORS, offline). */
export const NETWORK_ERROR = 'network_error'

function redirectToLogin() {
  tokens.clear()
  // Full navigation (we live outside the Router) — clears in-memory state too.
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// A single in-flight refresh shared across concurrent 401s, so we never fire
// multiple refreshes at once.
let refreshInFlight: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokens.refresh()
  if (!refresh) return null

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${BASE_URL}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refresh }),
        })
        if (!res.ok) return null
        const data = (await res.json()) as { access_token: string }
        tokens.setAccess(data.access_token)
        return data.access_token
      } catch {
        return null
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

interface RequestOptions {
  method?: string
  body?: unknown
  /** Set false for the auth endpoints, which must not carry a stale token. */
  auth?: boolean
  // An array value emits one `?key=v` per element (repeated query param, the
  // shape FastAPI expects for `list[...]` query params — see /explore filters
  // in E11-S1).
  query?: Record<string, string | number | string[] | undefined>
}

async function rawRequest(path: string, opts: RequestOptions, accessToken: string | null): Promise<Response> {
  const url = new URL(`${BASE_URL}${path}`)
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v === undefined || v === '') continue
      if (Array.isArray(v)) {
        for (const item of v) url.searchParams.append(k, item)
      } else {
        url.searchParams.set(k, String(v))
      }
    }
  }

  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.auth !== false && accessToken) headers['Authorization'] = `Bearer ${accessToken}`

  return fetch(url.toString(), {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  })
}

/**
 * Perform an API request with auth + refresh + typed errors.
 * Returns parsed JSON, or `undefined` for 204 No Content responses.
 */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  let res: Response
  try {
    res = await rawRequest(path, opts, tokens.access())
  } catch {
    throw new ApiError(0, NETWORK_ERROR, 'Cannot reach the server. Check your connection.')
  }

  // Try a one-shot token refresh on 401 for authenticated requests.
  if (res.status === 401 && opts.auth !== false) {
    const fresh = await refreshAccessToken()
    if (fresh) {
      try {
        res = await rawRequest(path, opts, fresh)
      } catch {
        throw new ApiError(0, NETWORK_ERROR, 'Cannot reach the server. Check your connection.')
      }
    }
    if (res.status === 401) {
      redirectToLogin()
      throw new ApiError(401, 'unauthorized', 'Your session has expired. Please sign in again.')
    }
  }

  if (res.status === 204) return undefined as T

  let payload: unknown = null
  const text = await res.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!res.ok) {
    const body = payload as { error?: string; message?: string } | null
    throw new ApiError(
      res.status,
      body?.error ?? 'error',
      body?.message ?? `Request failed (${res.status})`,
    )
  }

  return payload as T
}
