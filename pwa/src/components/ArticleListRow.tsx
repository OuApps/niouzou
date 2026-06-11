import { useState } from 'react'
import { ScoreBadge } from './ScoreBadge'
import { ScoreDebugSheet } from './ScoreDebugSheet'
import { FeedbackStateIcons } from './FeedbackStateIcons'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { useFeedbackStore } from '../store/feedback'
import type { FeedArticle } from '../types/api'

interface Props {
  article: FeedArticle
  /** Timestamp to display (e.g. `seen_at` for Explore History, `published_at` elsewhere). */
  timestamp: string | null
  onClick: () => void
  /**
   * Show the feedback-state icon row beneath the title. Off by default — the
   * Explore "New" tab disables it since every item is in the default state.
   */
  showState?: boolean
  /**
   * Mirror the Saved-screen treatment: always show the Bookmark as active.
   * (Being in the list IS the definition of saved.)
   */
  forceSaved?: boolean
}

/**
 * Reusable list row for Saved + Explore (E9 review refactor). Subscribes
 * directly to the feedback store so each row re-renders independently when
 * its own overlay flips — the parent screen no longer needs to subscribe to
 * the full overlay map just to keep the icons in sync.
 */
export const ArticleListRow = ({
  article,
  timestamp,
  onClick,
  showState = false,
  forceSaved = false,
}: Props) => {
  const override = useFeedbackStore((s) => s.overrides[article.id])
  const [debugOpen, setDebugOpen] = useState(false)
  const state =
    override ?? {
      reaction: article.reaction,
      is_saved: article.is_saved,
      read_full_article: article.read_full_article,
    }

  return (
    <>
    <button
      onClick={onClick}
      className="glass-sm flex items-start gap-3 w-full text-left"
      style={{
        borderRadius: 16,
        padding: 12,
        cursor: 'pointer',
        border: '1px solid rgba(255,255,255,0.10)',
        background: 'var(--glass-bg)',
      }}
    >
      {article.og_image_url && (
        <img
          src={article.og_image_url}
          alt=""
          style={{
            width: 64,
            height: 64,
            borderRadius: 10,
            objectFit: 'cover',
            flexShrink: 0,
          }}
        />
      )}
      <div className="flex-1 min-w-0">
        <div
          className="flex items-center gap-2"
          style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4 }}
        >
          <span
            title={article.source.name}
            style={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              minWidth: 0,
              flexShrink: 1,
            }}
          >
            {article.source.name}
          </span>
          <span style={{ flexShrink: 0 }}>
            <ScoreBadge
              keywordScore={article.keyword_score}
              keywordColdStart={article.keyword_cold_start}
              smartScore={article.smart_score}
              smartColdStart={article.smart_cold_start}
              activeMethod={article.active_method}
              onClick={() => setDebugOpen(true)}
            />
          </span>
        </div>
        <h3
          title={article.title}
          style={{
            fontSize: 13,
            fontWeight: 600,
            lineHeight: 1.35,
            margin: '0 0 6px',
            color: 'var(--text-primary)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            wordBreak: 'break-word',
          }}
        >
          {article.title}
        </h3>
        {showState && (
          <FeedbackStateIcons state={state} forceSaved={forceSaved} />
        )}
        <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 4 }}>
          {timestamp ? formatTimeAgo(timestamp) : ''}
        </p>
      </div>
    </button>
    {/* Sheet sits as a portal-like sibling so its overlay covers the whole
        screen and its inputs aren't nested inside the row's <button>. */}
    <ScoreDebugSheet
      articleId={debugOpen ? article.id : null}
      onClose={() => setDebugOpen(false)}
    />
    </>
  )
}
