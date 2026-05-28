import { create } from 'zustand'
import type { FeedArticle, FeedbackAction, SavedArticle } from '../types/api'

/**
 * Optimistic, in-memory overlay of the feedback the user has given this
 * session. The API is the source of truth (POST /feedback persists it); this
 * store just lets the save toggle stay consistent across navigation without a
 * refetch. Starts empty — seeded from the server's `feedback` where available.
 *
 * When `action === 'save'` we also stash the full article so the Saved screen
 * can show it immediately without a refetch (E7-S11). On any other action the
 * stash is dropped — Saved.tsx already filters those rows out.
 */
interface FeedbackState {
  feedbacks: Record<string, FeedbackAction>
  savedArticles: Record<string, SavedArticle>
  setFeedback: (articleId: string, action: FeedbackAction, article?: FeedArticle) => void
  removeFeedback: (articleId: string) => void
}

export const useFeedbackStore = create<FeedbackState>((set) => ({
  feedbacks: {},
  savedArticles: {},
  setFeedback: (articleId, action, article) =>
    set((state) => {
      const savedArticles = { ...state.savedArticles }
      if (action === 'save' && article) {
        savedArticles[articleId] = { ...article, saved_at: new Date().toISOString() }
      } else {
        delete savedArticles[articleId]
      }
      return {
        feedbacks: { ...state.feedbacks, [articleId]: action },
        savedArticles,
      }
    }),
  removeFeedback: (articleId) =>
    set((state) => {
      const rest = { ...state.feedbacks }
      delete rest[articleId]
      const savedArticles = { ...state.savedArticles }
      delete savedArticles[articleId]
      return { feedbacks: rest, savedArticles }
    }),
}))
