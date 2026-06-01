import { ChevronDown } from 'lucide-react'

/**
 * Pedagogical end-of-slide marker (E9-S2). Sits at the bottom of every fullscreen
 * feed slide so users learn that the next article is one more scroll away.
 *
 * The chevron bounces softly until the next slide enters the viewport — the
 * containing slide flips `data-bouncing` on the wrapper via IntersectionObserver
 * so we stop animating once the message has landed. CSS keyframe lives in
 * `pwa/src/index.css` (`@keyframes bounce-soft`).
 */
interface Props {
  /** True while the next slide is NOT yet visible — drives the bounce. */
  bouncing: boolean
}

export const ScrollBoundaryHint = ({ bouncing }: Props) => (
  <div
    data-bouncing={bouncing ? 'true' : 'false'}
    className="flex flex-col items-center"
    style={{ gap: 6, padding: '20px 0 8px', pointerEvents: 'none' }}
  >
    <div
      style={{
        width: '60%',
        maxWidth: 220,
        height: 1,
        background: 'rgba(255,255,255,0.10)',
        marginBottom: 10,
      }}
    />
    <div
      className="boundary-chevron"
      style={{ color: 'var(--text-tertiary)', display: 'inline-flex' }}
    >
      <ChevronDown size={20} strokeWidth={2.25} />
    </div>
    <span
      style={{
        fontSize: 12,
        color: 'var(--text-tertiary)',
        opacity: 0.5,
        letterSpacing: 0.2,
      }}
    >
      Article suivant
    </span>
  </div>
)
