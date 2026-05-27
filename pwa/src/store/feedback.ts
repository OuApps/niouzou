import { create } from 'zustand'
import type { FeedbackAction } from '../types/api'
import { MOCK_SAVED } from '../mocks/articles'

interface FeedbackState {
  feedbacks: Record<string, FeedbackAction>
  setFeedback: (articleId: string, action: FeedbackAction) => void
  removeFeedback: (articleId: string) => void
}

const initialFeedbacks: Record<string, FeedbackAction> = {}
for (const article of MOCK_SAVED) {
  initialFeedbacks[article.id] = 'save'
}

export const useFeedbackStore = create<FeedbackState>((set) => ({
  feedbacks: initialFeedbacks,
  setFeedback: (articleId, action) =>
    set((state) => ({
      feedbacks: { ...state.feedbacks, [articleId]: action },
    })),
  removeFeedback: (articleId) =>
    set((state) => {
      const { [articleId]: _, ...rest } = state.feedbacks
      return { feedbacks: rest }
    }),
}))
