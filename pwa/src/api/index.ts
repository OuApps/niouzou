// Typed endpoint functions for the Niouzou API.
// One function per endpoint in docs/API_SPEC.md. Screens import from here only.

import { ApiError, request, streamRequest, tokens } from './http'
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

// E17-S3 — text search spans seen + unseen, so seen_at is optional.
export interface ExploreSearchArticle extends FeedArticle {
  seen_at: string | null
}

export interface ExploreSearchPage extends Page {
  articles: ExploreSearchArticle[]
}

export interface ExploreOptions {
  cursor?: string
  limit?: number
  /** E11-S1 — filter to active score ≥ minScore (cold/NULL bypasses). */
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

// E17-S3 — text search over all the user's enriched articles.
export function getExploreSearch(
  q: string,
  cursor?: string,
  limit = 20,
): Promise<ExploreSearchPage> {
  return request<ExploreSearchPage>('/explore/search', {
    query: { q, cursor, limit },
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

// E17-S5 — counts returned by POST /feedback/reset.
export interface RecoResetResponse {
  reactions_cleared: number
  weights_deleted: number
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

// E17-S5 — wipe the user's learned reco signal (reactions + learned weights).
// Saved articles, read flags and pinned keywords are preserved server-side.
export function resetReco(): Promise<RecoResetResponse> {
  return request<RecoResetResponse>('/feedback/reset', { method: 'POST' })
}

// ── Articles ─────────────────────────────────────────────────────────────────

// E10-S2 — Score debug panel. One entry per article keyword; ``weight`` is
// ``null`` when the user has no row in ``keyword_weights`` for that term yet
// (renders as a dash in the bottom sheet).
export interface ScoreDebugKeyword {
  term: string
  weight: number | null
}

// E16-S7 — smart-mode breakdown: one k-NN neighbour of the scored article.
export interface ScoreDebugNeighbor {
  title: string
  similarity: number
  value: number
  age_days: number
  contribution: number
}

export interface ScoreDebugPin {
  term: string
  weight: number
  salience: number
  contribution: number
}

export interface ScoreDebug {
  // E16-S10 — both methods are always present so the panel shows the two
  // sections side by side, whatever the active mode.
  keyword_score: number | null
  keyword_cold_start: boolean
  smart_score: number | null
  smart_cold_start: boolean
  active_method: 'keyword' | 'smart'
  enrichment_model: string | null
  keywords: ScoreDebugKeyword[]
  liked_neighbors: ScoreDebugNeighbor[]
  disliked_neighbors: ScoreDebugNeighbor[]
  pins: ScoreDebugPin[]
}

export function getScoreDebug(articleId: string): Promise<ScoreDebug> {
  return request<ScoreDebug>(`/articles/${articleId}/score-debug`)
}

// ── Article chat (E21-S2/S4) ────────────────────────────────────────────────

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatDoneInfo {
  model: string
  prompt_tokens: number
  completion_tokens: number
}

export interface ChatStreamHandlers {
  /** One incremental text fragment of the assistant reply. */
  onToken: (delta: string) => void
  /** Stream completed normally. */
  onDone?: (info: ChatDoneInfo) => void
  /** Upstream failure *mid-stream* (HTTP status was already 200). Pre-stream
   *  failures (403/404/409/422/network) reject the promise with ApiError. */
  onError?: (message: string) => void
}

/**
 * POST /articles/{id}/chat — stream the LLM reply for the given thread.
 * v1 is stateless: pass the whole conversation (ending with a user turn) on
 * every call. Resolves when the stream ends; abort via `signal` to cancel
 * (closing the sheet, sending a new message).
 */
export async function streamArticleChat(
  articleId: string,
  messages: ChatTurn[],
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await streamRequest(
    `/articles/${articleId}/chat`,
    { method: 'POST', body: { messages } },
    signal,
  )
  const reader = res.body?.getReader()
  if (!reader) throw new ApiError(0, 'stream_error', 'Streaming not supported.')

  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE events are separated by a blank line.
    for (;;) {
      const boundary = buffer.indexOf('\n\n')
      if (boundary === -1) break
      const rawEvent = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      let event = 'message'
      let data = ''
      for (const line of rawEvent.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let payload: unknown
      try {
        payload = JSON.parse(data)
      } catch {
        continue
      }
      if (event === 'token') {
        const delta = (payload as { delta?: string }).delta
        if (delta) handlers.onToken(delta)
      } else if (event === 'done') {
        handlers.onDone?.(payload as ChatDoneInfo)
      } else if (event === 'error') {
        const err = payload as { message?: string }
        handlers.onError?.(err.message ?? 'The assistant is unavailable.')
      }
    }
  }
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
  // E16-S5/S9 — active score selector; drives the Smart Match banner on
  // Keywords.
  scoring_mode: 'keyword' | 'smart'
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

// E10-S7 — OpenRouter bill, summed over trailing windows.
export interface LLMCostWindow {
  window_hours: number
  cost_usd: number
}

export interface LLMCostStats {
  windows: LLMCostWindow[]
}

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
    last_error: string | null
    last_error_at: string | null
  }
  // Global pipeline telemetry (E10-S1) — drives the System panel.
  pipeline: PipelineStats
  // Global OpenRouter cost over 1h/6h/24h (E10-S7) — drives the System panel.
  llm_cost: LLMCostStats
}

// E19-S7 — admin-only now (returns 403 for non-admins). Non-admins use
// getFeedFreshness instead.
export function getStats(pipelineWindow: PipelineWindow = '6h'): Promise<Stats> {
  return request<Stats>(`/stats?pipeline_window=${pipelineWindow}`)
}

// E19-S7 — lightweight feed-freshness signal for every user. No cost, no
// pipeline errors, no run trigger — just enough to tell whether new content
// is on its way.
export interface FeedFreshness {
  pipeline_status: string
  pending_enrichment: number
  last_completed_at: string | null
}

export function getFeedFreshness(): Promise<FeedFreshness> {
  return request<FeedFreshness>('/stats/freshness')
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
  // E21-S1 — model used by the article chat (falls back to openrouter_model
  // server-side when unset).
  chat_model: string
  // E21-S7 — OpenRouter web plugin on chat completions (internet search).
  chat_web_search: boolean
  openrouter_api_key: string | null
  max_keywords_per_article: number
  cron_fetch_interval: number
  cron_nightly_refresh_hour: number
  score_threshold: number
  // Anti echo chamber: share (0-1) of sub-threshold articles randomly surfaced.
  random_surface_rate: number
  enrichment_input_max_chars: number
  // E16-S4/S9 — active score selector + instance-wide embedding coverage.
  scoring_mode: 'keyword' | 'smart'
  embeddings_done: number
  articles_total: number
}

export interface AdminConfigPatch {
  openrouter_model?: string
  chat_model?: string
  chat_web_search?: boolean
  openrouter_api_key?: string
  max_keywords_per_article?: number
  cron_fetch_interval?: number
  cron_nightly_refresh_hour?: number
  score_threshold?: number
  random_surface_rate?: number
  enrichment_input_max_chars?: number
  scoring_mode?: 'keyword' | 'smart'
}

export interface AdminModel {
  id: string
  name: string
  input_price_per_m: number
  output_price_per_m: number
  context_length: number
  // E21-S7 — capability flags for the chat selector. `web_search` marks
  // *native* search; any model can also search via the chat_web_search
  // plugin toggle.
  reasoning: boolean
  web_search: boolean
}

export function getAdminConfig(): Promise<AdminConfig> {
  return request<AdminConfig>('/admin/config')
}

export function patchAdminConfig(body: AdminConfigPatch): Promise<AdminConfig> {
  return request<AdminConfig>('/admin/config', { method: 'PATCH', body })
}

export function getAdminModels(
  usage: 'enrichment' | 'chat' = 'enrichment',
): Promise<AdminModel[]> {
  return request<AdminModel[]>('/admin/models', { query: { usage } })
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
