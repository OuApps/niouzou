export type FeedbackAction = 'like' | 'dislike' | 'skip' | 'save'

export interface SourceRef {
  id: string
  name: string
}

export interface SourceFull {
  id: string
  name: string
  url: string
  created_at: string
}

export type Scorer = 'tfidf' | 'ai_keyword'

export interface FeedArticle {
  id: string
  title: string
  summary_short: string
  og_image_url: string | null
  url: string
  source: SourceRef
  published_at: string
  relevance_score: number
  scorer?: Scorer | null
  keywords?: string[]
  read_time_minutes?: number
  // Set by the server when the stored content looks like a paywall teaser
  // (E7-S21). The PWA uses it to badge the card / detail view.
  is_premium?: boolean
}

export interface ArticleDetail {
  id: string
  title: string
  url: string
  summary_short: string
  summary_executive: string | null
  og_image_url: string | null
  source: SourceRef & { url: string }
  published_at: string
  enriched_at: string | null
  relevance_score: number
  scorer?: Scorer | null
  feedback: { action: FeedbackAction; updated_at: string } | null
  keywords?: string[]
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
