// Typed endpoint functions for the Niouzou API.
// One function per endpoint in docs/API_SPEC.md. Screens import from here only.

import { request, tokens } from './http'
import type {
  ArticleDetail,
  AuthTokens,
  FeedArticle,
  FeedbackAction,
  KeywordWeight,
  SavedArticle,
  SourceFull,
} from '../types/api'

export { ApiError, tokens } from './http'

// ── Generic paginated envelope ──────────────────────────────────────────────

interface Page {
  next_cursor: string | null
  has_more: boolean
}

export interface FeedPage extends Page {
  articles: FeedArticle[]
}
export interface SavedPage extends Page {
  articles: SavedArticle[]
}
export interface KeywordsPage extends Page {
  keywords: KeywordWeight[]
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<AuthTokens> {
  const data = await request<AuthTokens>('/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: false,
  })
  tokens.set(data.access_token, data.refresh_token, email)
  return data
}

export async function register(email: string, password: string): Promise<AuthTokens> {
  const data = await request<AuthTokens>('/auth/register', {
    method: 'POST',
    body: { email, password },
    auth: false,
  })
  tokens.set(data.access_token, data.refresh_token, email)
  return data
}

// ── Feed ───────────────────────────────────────────────────────────────────

export function getFeed(
  cursor?: string,
  limit = 20,
  minScore?: number,
): Promise<FeedPage> {
  return request<FeedPage>('/feed', {
    query: { cursor, limit, min_score: minScore },
  })
}

export function postImpression(articleId: string): Promise<void> {
  return request<void>(`/feed/${articleId}/impression`, { method: 'POST' })
}

// ── Feedback ─────────────────────────────────────────────────────────────────

export function postFeedback(articleId: string, action: FeedbackAction) {
  return request<{ article_id: string; action: FeedbackAction; updated_at: string }>('/feedback', {
    method: 'POST',
    body: { article_id: articleId, action },
  })
}

// ── Articles ─────────────────────────────────────────────────────────────────

export function getArticle(id: string): Promise<ArticleDetail> {
  return request<ArticleDetail>(`/articles/${id}`)
}

// ── Saved ──────────────────────────────────────────────────────────────────

export function getSaved(cursor?: string, limit = 20): Promise<SavedPage> {
  return request<SavedPage>('/saved', { query: { cursor, limit } })
}

// ── Sources ──────────────────────────────────────────────────────────────────

export function getSources(): Promise<{ sources: SourceFull[] }> {
  return request<{ sources: SourceFull[] }>('/sources')
}

export function addSource(
  url: string,
  fetchFullContent = false,
): Promise<SourceFull> {
  return request<SourceFull>('/sources', {
    method: 'POST',
    body: { url, fetch_full_content: fetchFullContent },
  })
}

export function updateSource(
  id: string,
  body: { fetch_full_content: boolean },
): Promise<SourceFull> {
  return request<SourceFull>(`/sources/${id}`, { method: 'PATCH', body })
}

export function deleteSource(id: string): Promise<void> {
  return request<void>(`/sources/${id}`, { method: 'DELETE' })
}

// ── Me ───────────────────────────────────────────────────────────────────────

export interface Me {
  email: string
  is_admin: boolean
  saved_count: number
  keyword_count: number
  source_count: number
}

export function getMe(): Promise<Me> {
  return request<Me>('/me')
}

// ── Keywords ─────────────────────────────────────────────────────────────────

export function getKeywords(cursor?: string, limit = 50): Promise<KeywordsPage> {
  return request<KeywordsPage>('/keywords', { query: { cursor, limit } })
}

export function patchKeyword(
  term: string,
  body: { weight?: number; manually_overridden?: boolean },
): Promise<KeywordWeight> {
  return request<KeywordWeight>(`/keywords/${encodeURIComponent(term)}`, {
    method: 'PATCH',
    body,
  })
}

export function resetKeywords(): Promise<void> {
  return request<void>('/keywords', { method: 'DELETE' })
}

// ── Stats / Admin (E7-S15, E7-S16) ───────────────────────────────────────────

export interface Stats {
  articles: {
    total: number
    pending_enrichment: number
    last_fetched_at: string | null
  }
  sources: { total: number; active: number }
  keywords: { total: number; manually_overridden: number }
  enrichment: {
    last_enriched_at: string | null
    total_ai: number
    total_tfidf: number
    total_tfidf_fallback: number
    last_error: string | null
    last_error_at: string | null
  }
}

export function getStats(): Promise<Stats> {
  return request<Stats>('/stats')
}

export function triggerRefresh(): Promise<{ status: string }> {
  return request<{ status: string }>('/admin/refresh', { method: 'POST' })
}
