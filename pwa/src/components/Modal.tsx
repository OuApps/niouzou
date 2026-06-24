import { useEffect } from 'react'
import type { ReactNode } from 'react'

interface ModalProps {
  /** Called on backdrop click and on Escape. */
  onClose: () => void
  children: ReactNode
  /** Panel max width in px. Defaults to 420. */
  maxWidth?: number
  /** Accessible label / dialog title id pass-through (optional). */
  ariaLabel?: string
}

/**
 * Shared centred dialog (E19-S2). One backdrop + panel treatment for every
 * popup so the admin modals stop diverging (opacity, blur, z-index, surface).
 * Closes on backdrop click and on Escape; the panel stops propagation so
 * clicks inside never bubble to the backdrop.
 *
 * Not for the feed's ScoreDebugSheet — that's a bottom sheet, a deliberately
 * different pattern.
 */
export const Modal = ({ onClose, children, maxWidth = 420, ariaLabel }: ModalProps) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        zIndex: 60,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="glass"
        style={{
          width: '100%',
          maxWidth,
          borderRadius: 20,
          background: 'rgba(12, 16, 24, 0.98)',
          padding: 18,
          maxHeight: '85vh',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {children}
      </div>
    </div>
  )
}
