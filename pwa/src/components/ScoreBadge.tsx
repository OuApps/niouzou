interface ScoreBadgeProps {
  score: number
  className?: string
}

export const ScoreBadge = ({ score, className = '' }: ScoreBadgeProps) => (
  <span
    className={className}
    style={{
      display: 'inline-flex',
      alignItems: 'center',
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
  </span>
)
