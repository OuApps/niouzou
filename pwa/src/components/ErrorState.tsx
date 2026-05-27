import { WifiOff } from 'lucide-react'

interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export const ErrorState = ({ message, onRetry }: ErrorStateProps) => (
  <div className="flex flex-col items-center justify-center py-20 px-8 text-center">
    <div
      className="flex items-center justify-center mb-4"
      style={{
        width: 64,
        height: 64,
        borderRadius: '50%',
        background: 'rgba(248, 113, 113, 0.10)',
        color: 'var(--action-dislike)',
      }}
    >
      <WifiOff size={26} />
    </div>
    <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>Something went wrong</h3>
    <p style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 260, marginBottom: 16 }}>
      {message}
    </p>
    {onRetry && (
      <button
        onClick={onRetry}
        style={{
          padding: '10px 20px',
          borderRadius: 12,
          background: 'var(--accent)',
          color: '#0c1018',
          border: 'none',
          fontSize: 13,
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        Try again
      </button>
    )}
  </div>
)
