interface KeywordTagProps {
  term: string
}

export const KeywordTag = ({ term }: KeywordTagProps) => (
  <span
    style={{
      display: 'inline-block',
      padding: '3px 10px',
      borderRadius: 20,
      background: 'rgba(255, 255, 255, 0.06)',
      color: 'var(--text-secondary)',
      fontSize: 10,
      fontWeight: 400,
      lineHeight: 1.4,
    }}
  >
    {term}
  </span>
)
