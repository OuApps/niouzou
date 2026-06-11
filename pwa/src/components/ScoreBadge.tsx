import { Hash, Radar } from 'lucide-react'
import type { MouseEvent } from 'react'
import type { ScoringMethod } from '../types/api'

// E16-S10 — two chips side by side, one per scoring method, so the user can
// compare them at a glance. The chip whose method is active (drives the feed
// filter + ranking, per `scoring_mode`) is highlighted with the solid accent
// pill; the other is muted (FilterChip's inactive recipe). A method renders
// «–» when its score is NULL (no keywords / no embedding for this article)
// or when it is cold-start for this user — same E10-S4 reasoning as before:
// the neutral ~50 % output would be misleading, not informative.

const METHODS: {
  id: ScoringMethod
  Icon: typeof Hash
  label: string
}[] = [
  { id: 'keyword', Icon: Hash, label: 'Keyword score' },
  { id: 'smart', Icon: Radar, label: 'Smart Match score' },
]

interface ScoreBadgeProps {
  keywordScore: number | null
  keywordColdStart?: boolean
  smartScore: number | null
  smartColdStart?: boolean
  activeMethod: ScoringMethod
  className?: string
  // E10-S2 — when provided, the badge renders as a button and triggers the
  // score debug panel. The caller is responsible for calling
  // ``stopPropagation`` on the synthetic event — but we do it here too so
  // callers can't forget and let the tap reach the TikTok slide gestures
  // behind the badge.
  onClick?: (event: MouseEvent<HTMLElement>) => void
}

const chipText = (score: number | null, coldStart: boolean): string =>
  score === null || coldStart ? '–' : `${Math.round(score * 100)}%`

export const ScoreBadge = ({
  keywordScore,
  keywordColdStart = false,
  smartScore,
  smartColdStart = false,
  activeMethod,
  className = '',
  onClick,
}: ScoreBadgeProps) => {
  const Tag: 'button' | 'span' = onClick ? 'button' : 'span'
  const handleClick = onClick
    ? (event: MouseEvent<HTMLElement>) => {
        event.stopPropagation()
        onClick(event)
      }
    : undefined
  const values: Record<ScoringMethod, string> = {
    keyword: chipText(keywordScore, keywordColdStart),
    smart: chipText(smartScore, smartColdStart),
  }
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
        padding: 0,
        background: 'transparent',
        border: 'none',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      {METHODS.map(({ id, Icon, label }) => {
        const active = id === activeMethod
        return (
          <span
            key={id}
            aria-label={`${label}: ${values[id]}${active ? ' (active)' : ''}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '3px 8px',
              borderRadius: 20,
              fontSize: 11,
              fontWeight: 600,
              lineHeight: 1,
              background: active ? 'var(--accent)' : 'rgba(255, 255, 255, 0.05)',
              color: active ? '#0c1018' : 'var(--text-secondary)',
              border: active
                ? '1px solid var(--accent)'
                : '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            <Icon size={11} style={{ color: 'inherit' }} />
            {values[id]}
          </span>
        )
      })}
    </Tag>
  )
}
