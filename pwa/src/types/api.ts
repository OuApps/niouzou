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

export interface SourceFull {
  id: string
  name: string
  url: string
  created_at: string
  fetch_full_content: boolean
  active: boolean
}

export type Scorer = 'tfidf' | 'ai_keyword'

export interface FeedArticle extends FeedbackState {
  id: string
  title: string
  summary_short: string
  // Full crawled content (E9-S2 renders it inline when present).
  content?: string | null
  // Bullet-point exec summary, AI-only (null without OpenRouter).
  summary_executive?: string | null
  og_image_url: string | null
  url: string
  source: SourceRef
  published_at: string
  relevance_score: number
  scorer?: Scorer | null
  // OpenRouter model id when the article was AI-enriched (E10-S2). Null on
  // TF-IDF (native or fallback) and on pre-E10-S2 rows. Shown in the score
  // debug bottom sheet.
  enrichment_model?: string | null
  // E10-S4 — true when none of the article's keywords has a user weight
  // yet. The ScoreBadge renders ``New`` instead of the neutral percentage,
  // and the server passes the article through regardless of the configured
  // score_threshold.
  is_cold_start?: boolean
  keywords?: string[]
  read_time_minutes?: number
  // Set by the server when the stored content looks like a paywall teaser
  // (E7-S21). The PWA uses it to badge the card / detail view.
  is_premium?: boolean
}

export interface SavedArticle extends FeedArticle {
  saved_at: string
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
