import { Bookmark, BookOpen, ThumbsDown, ThumbsUp } from 'lucide-react'
import type { FeedbackState } from '../types/api'

interface Props {
  state: FeedbackState
  /**
   * Force `Bookmark` to look active even when `state.is_saved` is false. Used
   * by the Saved screen, where being in the list IS the definition of saved
   * and the icon is decorative.
   */
  forceSaved?: boolean
}

/**
 * Compact row of feedback-state icons (E9-S2/S3) — used by Saved and Explore
 * History to mirror what the user has done with an article without having to
 * tap into the fullscreen slide.
 */
export const FeedbackStateIcons = ({ state, forceSaved = false }: Props) => {
  const saved = forceSaved || state.is_saved
  return (
    <div className="flex items-center" style={{ gap: 10 }}>
      <Bookmark
        size={13}
        style={{
          color: saved ? 'var(--action-save)' : 'var(--text-tertiary)',
          fill: saved ? 'var(--action-save)' : 'none',
          opacity: saved ? 1 : 0.5,
        }}
      />
      <ThumbsUp
        size={13}
        style={{
          color:
            state.reaction === 'like'
              ? 'var(--action-like)'
              : 'var(--text-tertiary)',
          fill: state.reaction === 'like' ? 'var(--action-like)' : 'none',
          opacity: state.reaction === 'like' ? 1 : 0.5,
        }}
      />
      <ThumbsDown
        size={13}
        style={{
          color:
            state.reaction === 'dislike'
              ? 'var(--action-dislike)'
              : 'var(--text-tertiary)',
          fill:
            state.reaction === 'dislike' ? 'var(--action-dislike)' : 'none',
          opacity: state.reaction === 'dislike' ? 1 : 0.5,
        }}
      />
      <BookOpen
        size={13}
        style={{
          color: state.read_full_article
            ? 'var(--text-secondary)'
            : 'var(--text-tertiary)',
          opacity: state.read_full_article ? 1 : 0.5,
        }}
      />
    </div>
  )
}
