import { useEffect } from 'react'
import type { ReactNode } from 'react'

interface ModalProps {
  /** Called on backdrop click and on Escape. */
  onClose: () => void
  children: ReactNode
  /** Panel max width in px. Defaults to 320 (the app's confirm-dialog width). */
  maxWidth?: number
  /** Accessible label for the dialog. */
  ariaLabel?: string
}

/**
 * Shared centred dialog — the single source of truth for the app's confirm /
 * popup chrome (E19-S2, aligned to the canonical pattern in E19-S6). Reproduces
 * exactly the backdrop + glass panel used by the Keywords "Reset all" and
 * Profile "Reset recommendations" dialogs: dim `rgba(0,0,0,0.6)` backdrop (no
 * blur), `glass` panel on `--bg-elevated`, radius 20, padding 20. Closes on
 * backdrop click and Escape; the panel stops propagation.
 *
 * Children own their own internal layout (title / body / a `justify-end`
 * button row), matching the inline dialogs this replaces.
 *
 * Not for the feed's ScoreDebugSheet — that's a bottom sheet, a deliberately
 * different pattern.
 */
export const Modal = ({ onClose, children, maxWidth = 320, ariaLabel }: ModalProps) => {
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
        zIndex: 50,
        background: 'rgba(0, 0, 0, 0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="glass"
        style={{
          borderRadius: 20,
          padding: 20,
          maxWidth,
          width: '100%',
          maxHeight: '85vh',
          overflowY: 'auto',
          background: 'var(--bg-elevated, rgba(20,24,34,0.95))',
        }}
      >
        {children}
      </div>
    </div>
  )
}
