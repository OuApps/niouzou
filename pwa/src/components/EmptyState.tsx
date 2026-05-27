import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
}

export const EmptyState = ({ icon: Icon, title, description }: EmptyStateProps) => (
  <div className="flex flex-col items-center justify-center py-20 px-8 text-center">
    <div
      className="flex items-center justify-center mb-4"
      style={{
        width: 64,
        height: 64,
        borderRadius: '50%',
        background: 'var(--accent-subtle)',
        color: 'var(--accent)',
      }}
    >
      <Icon size={28} />
    </div>
    <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{title}</h3>
    <p style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 240 }}>{description}</p>
  </div>
)
