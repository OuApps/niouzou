// FilterChip (E11-S2) — chip used in the Explore filter bar for the Score
// and Sources rows. Active state mirrors the BottomNav / Tabs pattern:
// accent text on a subtle accent background, plus a thin accent border to
// distinguish it from the borderless inactive variant.

interface FilterChipProps {
  label: string
  active: boolean
  onClick: () => void
}

export const FilterChip = ({ label, active, onClick }: FilterChipProps) => (
  <button
    type="button"
    onClick={onClick}
    style={{
      flex: '0 0 auto',
      padding: '5px 12px',
      borderRadius: 16,
      fontSize: 11,
      fontWeight: 600,
      cursor: 'pointer',
      whiteSpace: 'nowrap',
      color: active ? 'var(--accent)' : 'var(--text-secondary)',
      background: active ? 'var(--accent-subtle)' : 'rgba(255, 255, 255, 0.05)',
      border: active
        ? '1px solid var(--accent)'
        : '1px solid rgba(255, 255, 255, 0.08)',
    }}
  >
    {label}
  </button>
)
