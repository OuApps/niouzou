import { create } from 'zustand'
import type { FeedbackAction } from '../types/api'

/**
 * Optimistic, in-memory overlay of the feedback the user has given this
 * session. The API is the source of truth (POST /feedback persists it); this
 * store just lets the save toggle stay consistent across navigation without a
 * refetch. Starts empty — seeded from the server's `feedback` where available.
 */
interface FeedbackState {
  feedbacks: Record<string, FeedbackAction>
  setFeedback: (articleId: string, action: FeedbackAction) => void
  removeFeedback: (articleId: string) => void
}

export const useFeedbackStore = create<FeedbackState>((set) => ({
  feedbacks: {},
  setFeedback: (articleId, action) =>
    set((state) => ({
      feedbacks: { ...state.feedbacks, [articleId]: action },
    })),
  removeFeedback: (articleId) =>
    set((state) => {
      const rest = { ...state.feedbacks }
      delete rest[articleId]
      return { feedbacks: rest }
    }),
}))
