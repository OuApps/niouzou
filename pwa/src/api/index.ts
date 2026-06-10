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

export interface ExploreOptions {
  cursor?: string
  limit?: number
  /** E11-S1 — filter to relevance_score ≥ minScore (cold-start bypasses). */
  minScore?: number
  /** E11-S1 — restrict to these source UUIDs (must belong to the user). */
  sourceIds?: string[]
}

export function getExploreHistory(
  opts: ExploreOptions = {},
): Promise<ExploreHistoryPage> {
  const { cursor, limit = 20, minScore, sourceIds } = opts
  return request<ExploreHistoryPage>('/explore/history', {
    query: {
      cursor,
      limit,
      min_score: minScore,
      source_ids: sourceIds && sourceIds.length > 0 ? sourceIds : undefined,
    },
  })
}

export function getExploreNew(
  opts: ExploreOptions = {},
): Promise<ExploreNewPage> {
  const { cursor, limit = 20, minScore, sourceIds } = opts
  return request<ExploreNewPage>('/explore/new', {
    query: {
      cursor,
      limit,
      min_score: minScore,
      source_ids: sourceIds && sourceIds.length > 0 ? sourceIds : undefined,
    },
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

// ── Articles ─────────────────────────────────────────────────────────────────

// E10-S2 — Score debug panel. One entry per article keyword; ``weight`` is
// ``null`` when the user has no row in ``keyword_weights`` for that term yet
// (renders as a dash in the bottom sheet).
export interface ScoreDebugKeyword {
  term: string
  weight: number | null
}

export interface ScoreDebug {
  relevance_score: number | null
  scorer: string | null
  enrichment_model: string | null
  keywords: ScoreDebugKeyword[]
}

export function getScoreDebug(articleId: string): Promise<ScoreDebug> {
  return request<ScoreDebug>(`/articles/${articleId}/score-debug`)
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
  fetchFullContent = true,
): Promise<SourceFull> {
  return request<SourceFull>('/sources', {
    method: 'POST',
    body: { url, fetch_full_content: fetchFullContent },
  })
}

export function updateSource(
  id: string,
  body: { fetch_full_content?: boolean; active?: boolean },
): Promise<SourceFull> {
  return request<SourceFull>(`/sources/${id}`, { method: 'PATCH', body })
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

export interface PipelineAggregates {
  // Echoes ?pipeline_window (in hours) so the PWA never has to translate
  // its own picker state into a header label.
  window_hours: number
  runs_count: number
  articles_fetched: number
  articles_enriched: number
  articles_failed: number
  // Null when no ``completed`` run exists in the window — render "—" rather
  // than "0s/article".
  avg_s_per_article: number | null
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
  // E10-S5 — windowed health summary for the admin System panel.
  aggregates: PipelineAggregates
}

// E10-S5 — closed set so the picker can drive the query directly. The
// backend rejects anything else with 422.
export type PipelineWindow = '1h' | '6h' | '24h'

export interface Stats {
  // E8-S3: surfaced so the PWA can render "Next run" against the live
  // setting rather than a hardcoded constant.
  cron_fetch_interval_minutes: number
  // E11-S1 — effective SCORE_THRESHOLD; powers the "≥ seuil" chip in the
  // Explore filter bar. `0.0` means "no threshold configured" and hides
  // that chip.
  score_threshold: number
  articles: {
    total: number
    pending_enrichment: number
    last_fetched_at: string | null
  }
  sources: { total: number; active: number }
  keywords: {
    total: number
    manually_overridden: number
    // E10-S3 — global vocab size + last applied compaction + pending preview.
    distinct_keyword_count: number
    last_compact_at: string | null
    pending_compaction_id: string | null
  }
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

export function getStats(pipelineWindow: PipelineWindow = '6h'): Promise<Stats> {
  return request<Stats>(`/stats?pipeline_window=${pipelineWindow}`)
}

export function triggerRefresh(): Promise<{ status: string }> {
  return request<{ status: string }>('/admin/refresh', { method: 'POST' })
}

// ── Admin compaction (E10-S3) ───────────────────────────────────────────────

export interface CompactionGroup {
  canonical: string
  aliases: string[]
  // Annotated by the worker at apply time; the PWA shows pinned groups
  // greyed out in the preview modal so the admin knows they'll be left
  // untouched.
  skipped_reason?: string | null
}

export interface CompactionPreview {
  id: string
  groups: CompactionGroup[]
}

export function compactKeywordsPreview(): Promise<CompactionPreview> {
  return request<CompactionPreview>('/admin/compact-keywords/preview', {
    method: 'POST',
  })
}

// Resume a previously-generated preview (no LLM hop). Used when
// ``stats.keywords.pending_compaction_id`` points at a run the admin
// abandoned in a prior session.
export function compactKeywordsGet(id: string): Promise<CompactionPreview> {
  return request<CompactionPreview>(`/admin/compact-keywords/${id}`)
}

export function compactKeywordsApply(id: string): Promise<{ status: string }> {
  return request<{ status: string }>('/admin/compact-keywords/apply', {
    method: 'POST',
    body: { id },
  })
}

export function compactKeywordsReject(id: string): Promise<void> {
  return request<void>(`/admin/compact-keywords/${id}`, { method: 'DELETE' })
}

// ── Admin config (E8-S3 / E8-S4) ─────────────────────────────────────────────

export interface AdminConfig {
  openrouter_model: string
  openrouter_api_key: string | null
  max_keywords_per_article: number
  cron_fetch_interval: number
  cron_refresh_weights_hour: number
  score_threshold: number
  // E16-S4 — scoring engine + instance-wide embedding coverage.
  scoring_mode: 'classic' | 'smart'
  embeddings_done: number
  articles_total: number
}

export interface AdminConfigPatch {
  openrouter_model?: string
  openrouter_api_key?: string
  max_keywords_per_article?: number
  cron_fetch_interval?: number
  cron_refresh_weights_hour?: number
  score_threshold?: number
  scoring_mode?: 'classic' | 'smart'
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

export function deleteAdminUser(userId: string): Promise<void> {
  return request<void>(`/admin/users/${userId}`, { method: 'DELETE' })
}

// ── Admin LLM prompts (E13-S2) ───────────────────────────────────────────────

export interface LlmPrompt {
  name: string
  body: string
  updated_at: string
}

export function getAdminPrompts(): Promise<LlmPrompt[]> {
  return request<LlmPrompt[]>('/admin/prompts')
}

export function updateAdminPrompt(name: string, body: string): Promise<LlmPrompt> {
  return request<LlmPrompt>(`/admin/prompts/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    body: { body },
  })
}
