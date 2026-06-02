import { ChevronDown } from 'lucide-react'

/**
 * End-of-slide affordance for the TikTok-style feed (E9-S2, refined E10 UX).
 * Sits at the bottom of every slide and signals "the next article is below".
 *
 * Two interaction modes coexist:
 *   1. Swipe — scroll-snap on the parent ``.feed-snap`` carries the user
 *      to the next slide.
 *   2. Tap — when ``onActivate`` is provided, the chevron + label render
 *      as a button that programmatically snaps to the next slide. The same
 *      tap target covers both the icon and the label so there's no narrow
 *      hit zone (E10 follow-up: the previous unclickable hint was confusing
 *      to users who weren't sure where to scroll).
 *
 * The chevron bounces softly until the next slide enters the viewport — CSS
 * keyframe lives in ``pwa/src/index.css`` (``@keyframes bounce-soft``).
 */
interface Props {
  /** True while the next slide is NOT yet visible — drives the bounce. */
  bouncing: boolean
  /** Tap handler. When omitted, renders as a static hint (no button). */
  onActivate?: () => void
  /** Suppress the chevron + label when there's no next slide. */
  hidden?: boolean
}

export const ScrollBoundaryHint = ({ bouncing, onActivate, hidden }: Props) => {
  if (hidden) return null
  const inner = (
    <>
      <div
        style={{
          width: '60%',
          maxWidth: 220,
          height: 1,
          background: 'rgba(255,255,255,0.10)',
          marginBottom: 12,
        }}
      />
      <div
        className="boundary-chevron"
        style={{ color: 'var(--text-secondary)', display: 'inline-flex' }}
      >
        <ChevronDown size={22} strokeWidth={2.25} />
      </div>
      <span
        style={{
          fontSize: 13,
          color: 'var(--text-secondary)',
          letterSpacing: 0.2,
          fontWeight: 500,
        }}
      >
        Next article
      </span>
    </>
  )

  const sharedStyle: React.CSSProperties = {
    gap: 6,
    // Generous tap target — the chevron alone is ~22px and the label ~16px,
    // so the surrounding padding makes the whole region reactive.
    padding: '18px 24px',
    width: '100%',
    background: 'transparent',
    border: 'none',
    color: 'inherit',
    textAlign: 'center',
  }

  if (onActivate) {
    return (
      <button
        type="button"
        data-bouncing={bouncing ? 'true' : 'false'}
        onClick={onActivate}
        aria-label="Go to next article"
        className="flex flex-col items-center"
        style={{ ...sharedStyle, cursor: 'pointer' }}
      >
        {inner}
      </button>
    )
  }

  return (
    <div
      data-bouncing={bouncing ? 'true' : 'false'}
      className="flex flex-col items-center"
      style={{ ...sharedStyle, pointerEvents: 'none' }}
    >
      {inner}
    </div>
  )
}
