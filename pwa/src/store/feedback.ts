import { create } from 'zustand'
import type { FeedArticle, FeedbackState, Reaction, SavedArticle } from '../types/api'

const DEFAULT_STATE: FeedbackState = {
  reaction: 'none',
  is_saved: false,
  read_full_article: false,
}

/**
 * Optimistic, in-memory overlay of the feedback the user has given this
 * session (E9-S1/S2). The API is the source of truth; this store lets the
 * action buttons stay responsive across navigation without a re-fetch.
 *
 * `savedArticles` mirrors the FeedArticle payload for items the user just
 * saved, so the Saved screen can show them before the next refresh (E7-S11).
 * An item drops out of `savedArticles` as soon as `is_saved` flips back to
 * false in the overlay.
 */
interface FeedbackStoreState {
  overrides: Record<string, FeedbackState>
  savedArticles: Record<string, SavedArticle>
  /** Read the effective state for an article (overlay if present, else fallback). */
  get: (articleId: string, fallback?: FeedbackState) => FeedbackState
  /** Merge a partial update; mirrors `POST /feedback` semantics on the client. */
  apply: (
    articleId: string,
    patch: Partial<FeedbackState>,
    article?: FeedArticle,
  ) => FeedbackState
  /** Drop the override for an article (e.g. after a server error rollback). */
  remove: (articleId: string) => void
}

function fromArticle(article: FeedArticle): FeedbackState {
  return {
    reaction: article.reaction,
    is_saved: article.is_saved,
    read_full_article: article.read_full_article,
  }
}

function toSavedArticle(article: FeedArticle, state: FeedbackState): SavedArticle {
  return {
    ...article,
    ...state,
    saved_at: new Date().toISOString(),
  }
}

export const useFeedbackStore = create<FeedbackStoreState>((set, getStore) => ({
  overrides: {},
  savedArticles: {},
  get: (articleId, fallback) =>
    getStore().overrides[articleId] ?? fallback ?? DEFAULT_STATE,
  apply: (articleId, patch, article) => {
    const current = getStore().overrides[articleId] ?? (
      article ? fromArticle(article) : DEFAULT_STATE
    )
    // Monotone read: false never overrides a previous true (mirrors backend).
    const nextRead =
      patch.read_full_article === undefined
        ? current.read_full_article
        : current.read_full_article || patch.read_full_article
    const next: FeedbackState = {
      reaction: patch.reaction ?? current.reaction,
      is_saved: patch.is_saved ?? current.is_saved,
      read_full_article: nextRead,
    }
    set((state) => {
      const savedArticles = { ...state.savedArticles }
      if (next.is_saved && article) {
        savedArticles[articleId] = toSavedArticle(article, next)
      } else if (!next.is_saved) {
        delete savedArticles[articleId]
      }
      return {
        overrides: { ...state.overrides, [articleId]: next },
        savedArticles,
      }
    })
    return next
  },
  remove: (articleId) =>
    set((state) => {
      const overrides = { ...state.overrides }
      delete overrides[articleId]
      const savedArticles = { ...state.savedArticles }
      delete savedArticles[articleId]
      return { overrides, savedArticles }
    }),
}))

/** Build a partial-update payload for `POST /feedback` from a desired state diff. */
export function diffForPost(
  current: FeedbackState,
  next: FeedbackState,
): { reaction?: Reaction; is_saved?: boolean; read_full_article?: true } {
  const out: ReturnType<typeof diffForPost> = {}
  if (current.reaction !== next.reaction) out.reaction = next.reaction
  if (current.is_saved !== next.is_saved) out.is_saved = next.is_saved
  if (!current.read_full_article && next.read_full_article) {
    out.read_full_article = true
  }
  return out
}
