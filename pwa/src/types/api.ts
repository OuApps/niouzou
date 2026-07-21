// E9-S1 — reaction/save/read are independent dimensions on every article.
export type Reaction = 'like' | 'dislike' | 'none'

export interface FeedbackState {
  reaction: Reaction
  is_saved: boolean
  read_full_article: boolean
}

export interface SourceRef {
  id: string
  name: string
}

// E24 — compact tag shape embedded in SourceFull.tags.
export interface TagRef {
  id: string
  name: string
}

// E24 — per-user source tag; `threshold` is the tag's own feed relevance
// threshold (null = inherit the global SCORE_THRESHOLD).
export interface Tag {
  id: string
  name: string
  threshold: number | null
  source_count: number
}

export interface SourceFull {
  id: string
  name: string
  url: string
  created_at: string
  fetch_full_content: boolean
  active: boolean
  // E17-S6 — article volume for this source (total + last 24h).
  article_count_total: number
  article_count_24h: number
  // E24-S3 — tags attached to this source, sorted by name.
  tags: TagRef[]
}

// E16-S9 — the two persisted scoring methods; `scoring_mode` selects which
// one drives the feed filter + ranking.
export type ScoringMethod = 'keyword' | 'smart'

export interface FeedArticle extends FeedbackState {
  id: string
  title: string
  // Legacy 3-4 sentence brief. New articles never populate this — the bullet
  // ``summary_executive`` is the only AI summary going forward. Kept for
  // backward compat with already-enriched rows.
  summary_short?: string | null
  // Full crawled content (E9-S2 renders it inline when present).
  content?: string | null
  // Bullet-point exec summary, AI-only (null without OpenRouter).
  summary_executive?: string | null
  og_image_url: string | null
  url: string
  source: SourceRef
  published_at: string
  // E16-S8/S10 — both scores travel together so the card renders the two
  // chips side by side. Null = the method had no input for this article
  // (no keywords / no embedding); together with the cold flags it renders
  // as «–». `active_method` says which score drove the ranking.
  keyword_score: number | null
  keyword_cold_start: boolean
  smart_score: number | null
  smart_cold_start: boolean
  active_method: ScoringMethod
  // OpenRouter model id when the article was AI-enriched (E10-S2). Null when
  // the LLM was unavailable and on pre-E10-S2 rows. Shown in the score
  // debug bottom sheet.
  enrichment_model?: string | null
  keywords?: string[]
  read_time_minutes?: number
  // Set by the server when the stored content looks like a paywall teaser
  // (E7-S21). The PWA uses it to badge the card / detail view.
  is_premium?: boolean
}

export interface SavedArticle extends FeedArticle {
  saved_at: string
}

// E23-S3 — GET /articles/{id}. Structurally a FeedArticle (so it renders in
// FeedArticleSlide) plus `owned`: false when the article comes from a source
// the caller doesn't subscribe to (deep link / shared link) — the view then
// drops scoring + feedback and reads it as-is.
export interface ArticleDetail extends FeedArticle {
  enriched_at: string | null
  owned: boolean
}

export interface KeywordWeight {
  term: string
  weight: number
  like_count: number
  dislike_count: number
  manually_overridden: boolean
  updated_at: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}
