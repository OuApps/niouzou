import { Sparkles } from 'lucide-react'
import type { Scorer } from '../types/api'

interface ScoreBadgeProps {
  score: number
  scorer?: Scorer | null
  className?: string
}

export const ScoreBadge = ({ score, scorer, className = '' }: ScoreBadgeProps) => {
  // Only flag AI-scored articles. TF-IDF (and pre-E7-S7 null) shows the score
  // alone — TF-IDF is the baseline so calling it out adds noise.
  const isAi = scorer === 'ai_keyword'
  return (
    <span
      className={className}
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
      }}
    >
      {Math.round(score * 100)}%
      {isAi && (
        <Sparkles
          size={11}
          aria-label="Scored by AI"
          style={{ color: 'inherit' }}
        />
      )}
    </span>
  )
}
