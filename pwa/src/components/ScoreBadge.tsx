import { Hash, Radar, Sparkles } from 'lucide-react'
import type { MouseEvent } from 'react'
import type { Scorer } from '../types/api'

// Maps the persisted `scorer` column to the icon shown in the badge, so a
// glance at the feed tells you which engine produced the score.
const SCORER_ICONS: Record<Scorer, { Icon: typeof Sparkles; label: string }> = {
  ai_keyword: { Icon: Sparkles, label: 'Scored by AI' },
  smart_match: { Icon: Radar, label: 'Scored by Smart Match' },
  tfidf: { Icon: Hash, label: 'Scored by keywords' },
}

interface ScoreBadgeProps {
  score: number
  scorer?: Scorer | null
  className?: string
  // E10-S4 — when true, the badge renders a dash instead of a percentage.
  // Cold-start articles have no user signal on any of their keywords yet,
  // so the neutral 50 % output is misleading. We show "-" rather than "New"
  // to avoid confusion with a freshly-ingested article ("nouvel article").
  isColdStart?: boolean
  // E10-S2 — when provided, the badge renders as a button and triggers the
  // score debug panel. The caller is responsible for calling
  // ``stopPropagation`` on the synthetic event — but we do it here too so
  // callers can't forget and let the tap reach the TikTok slide gestures
  // behind the badge.
  onClick?: (event: MouseEvent<HTMLElement>) => void
}

export const ScoreBadge = ({
  score,
  scorer,
  className = '',
  isColdStart = false,
  onClick,
}: ScoreBadgeProps) => {
  // Pre-E7-S7 rows have no `scorer` recorded — show the score alone.
  const scorerIcon = scorer ? SCORER_ICONS[scorer] : null
  const Tag: 'button' | 'span' = onClick ? 'button' : 'span'
  const handleClick = onClick
    ? (event: MouseEvent<HTMLElement>) => {
        event.stopPropagation()
        onClick(event)
      }
    : undefined
  return (
    <Tag
      className={className}
      onClick={handleClick}
      type={onClick ? 'button' : undefined}
      aria-label={onClick ? 'Show score breakdown' : undefined}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '3px 8px',
        borderRadius: 20,
        background: 'var(--accent)',
        color: '#0c1018',
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1,
        border: 'none',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      {isColdStart ? '–' : `${Math.round(score * 100)}%`}
      {scorerIcon && (
        <scorerIcon.Icon
          size={11}
          aria-label={scorerIcon.label}
          style={{ color: 'inherit' }}
        />
      )}
    </Tag>
  )
}
