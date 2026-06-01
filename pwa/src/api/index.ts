// Typed endpoint functions for the Niouzou API.
// One function per endpoint in docs/API_SPEC.md. Screens import from here only.

import { request, tokens } from './http'
import type {
  AuthTokens,
  FeedArticle,
  FeedbackState,
  KeywordWeight,
  Reaction,
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
  cold_start?: boolean
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

export interface GetFeedOptions {
  cursor?: string
  limit?: number
  minScore?: number
  /** E9-S3 — pivot the first page on this article (Explore / Saved → Feed). */
  start?: string
}

export function getFeed(opts: GetFeedOptions = {}): Promise<FeedPage> {
  const { cursor, limit = 20, minScore, start } = opts
  return request<FeedPage>('/feed', {
    query: { cursor, limit, min_score: minScore, start },
  })
}

export function postImpression(articleId: string): Promise<void> {
  return request<void>(`/feed/${articleId}/impression`, { method: 'POST' })
}

// ── Explore (E9-S3) ─────────────────────────────────────────────────────────

export interface ExploreHistoryArticle extends FeedArticle {
  seen_at: string
}

export interface ExploreHistoryPage extends Page {
  articles: ExploreHistoryArticle[]
}

export interface ExploreNewPage extends Page {
  articles: FeedArticle[]
}

export function getExploreHistory(
  cursor?: string,
  limit = 20,
): Promise<ExploreHistoryPage> {
  return request<ExploreHistoryPage>('/explore/history', {
    query: { cursor, limit },
  })
}

export function getExploreNew(
  cursor?: string,
  limit = 20,
): Promise<ExploreNewPage> {
  return request<ExploreNewPage>('/explore/new', {
    query: { cursor, limit },
  })
}

// ── Feedback (E9-S1 partial update) ─────────────────────────────────────────

export interface FeedbackUpdate {
  reaction?: Reaction
  is_saved?: boolean
  // Monotone: send `true` to mark as read. `false` is silently dropped by the
  // backend, but never include it in a payload — it makes the empty-payload
  // detection slightly less efficient.
  read_full_article?: true
}

export interface FeedbackResponse extends FeedbackState {
  article_id: string
  updated_at: string
}

export function postFeedback(
  articleId: string,
  update: FeedbackUpdate,
): Promise<FeedbackResponse> {
  return request<FeedbackResponse>('/feedback', {
    method: 'POST',
    body: { article_id: articleId, ...update },
  })
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

// ── Stats / Admin (E7-S15, E7-S16, E8-S3, E10-S1) ───────────────────────────

export type PipelineStatus = 'running' | 'completed' | 'failed' | 'never_run'

export interface PipelineProgress {
  done: number
  total: number
}

export interface PipelineStats {
  status: PipelineStatus
  started_at: string | null
  completed_at: string | null
  articles_fetched: number
  articles_enriched: number
  articles_failed: number
  total_duration_s: number | null
  avg_s_per_article: number | null
  error: string | null
  in_progress: PipelineProgress | null
}

export interface Stats {
  // E8-S3: surfaced so the PWA can render "Next run" against the live
  // setting rather than a hardcoded constant.
  cron_fetch_interval_minutes: number
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
  // Global pipeline telemetry (E10-S1) — drives the System panel.
  pipeline: PipelineStats
}

export function getStats(): Promise<Stats> {
  return request<Stats>('/stats')
}

export function triggerRefresh(): Promise<{ status: string }> {
  return request<{ status: string }>('/admin/refresh', { method: 'POST' })
}

// ── Admin config (E8-S3 / E8-S4) ─────────────────────────────────────────────

export interface AdminConfig {
  openrouter_model: string
  openrouter_api_key: string | null
  max_keywords_per_article: number
  cron_fetch_interval: number
  cron_refresh_weights_hour: number
}

export interface AdminConfigPatch {
  openrouter_model?: string
  openrouter_api_key?: string
  max_keywords_per_article?: number
  cron_fetch_interval?: number
  cron_refresh_weights_hour?: number
}

export interface AdminModel {
  id: string
  name: string
  input_price_per_m: number
  output_price_per_m: number
  context_length: number
}

export function getAdminConfig(): Promise<AdminConfig> {
  return request<AdminConfig>('/admin/config')
}

export function patchAdminConfig(body: AdminConfigPatch): Promise<AdminConfig> {
  return request<AdminConfig>('/admin/config', { method: 'PATCH', body })
}

export function getAdminModels(): Promise<AdminModel[]> {
  return request<AdminModel[]>('/admin/models')
}

// ── Admin users (E8-S5) ──────────────────────────────────────────────────────

export interface AdminUser {
  id: string
  email: string
  is_admin: boolean
  created_at: string
}

export function getAdminUsers(): Promise<AdminUser[]> {
  return request<AdminUser[]>('/admin/users')
}

export function resetUserPassword(
  userId: string,
  newPassword: string,
): Promise<void> {
  return request<void>(`/admin/users/${userId}/password`, {
    method: 'PATCH',
    body: { new_password: newPassword },
  })
}
