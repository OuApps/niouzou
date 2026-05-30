import { create } from 'zustand'
import type { FeedArticle, SavedArticle } from '../types/api'

/**
 * In-memory snapshots of list screens (Feed and Saved) so that navigating to
 * an article detail and back doesn't reset the user's position (E7-S23).
 *
 * - Feed: `GET /feed` filters out articles with a recorded impression, so a
 *   naive re-fetch on remount drops the article the user just viewed and
 *   effectively advances the deck by one. The snapshot lets the Feed restore
 *   its loaded deck + index instead.
 * - Saved: a scrolled-down list reloads from page 1 on remount; the snapshot
 *   restores the previously-loaded pages and scroll position.
 *
 * Cleared on pull-to-refresh / explicit reload. Snapshots are not persisted
 * across full page reload — Zustand state is in-memory only.
 */
export interface FeedSnapshot {
  articles: FeedArticle[]
  cursor: string | null
  hasMore: boolean
  currentIndex: number
  goneIndices: number[]
  impressedIds: string[]
  minScore: number | null
}

export interface SavedSnapshot {
  articles: SavedArticle[]
  cursor: string | null
  hasMore: boolean
  scrollY: number
}

interface FeedStoreState {
  snapshot: FeedSnapshot | null
  savedSnapshot: SavedSnapshot | null
  // One-shot signal set by ArticleDetail when a like/dislike/save is submitted:
  // tells Feed to advance the deck past this article on remount. Back button
  // does not set this flag.
  advanceArticleId: string | null
  setSnapshot: (s: FeedSnapshot) => void
  clearSnapshot: () => void
  setSavedSnapshot: (s: SavedSnapshot) => void
  clearSavedSnapshot: () => void
  requestAdvance: (id: string) => void
  consumeAdvance: () => string | null
}

export const useFeedStore = create<FeedStoreState>((set, get) => ({
  snapshot: null,
  savedSnapshot: null,
  advanceArticleId: null,
  setSnapshot: (s) => set({ snapshot: s }),
  clearSnapshot: () => set({ snapshot: null }),
  setSavedSnapshot: (s) => set({ savedSnapshot: s }),
  clearSavedSnapshot: () => set({ savedSnapshot: null }),
  requestAdvance: (id) => set({ advanceArticleId: id }),
  consumeAdvance: () => {
    const id = get().advanceArticleId
    if (id !== null) set({ advanceArticleId: null })
    return id
  },
}))
