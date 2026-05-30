import { useRef } from 'react'
import { usePullToRefresh } from '../hooks/usePullToRefresh'

interface Props {
  /**
   * When provided, dragging upward from the bottom third of the viewport on
   * the background triggers this callback (E7-S19). The logo overlay spins
   * while the user pulls and continues spinning until the returned promise
   * resolves.
   */
  onRefresh?: () => void | Promise<void>
}

export const BlobBackground = ({ onRefresh }: Props) => {
  const ref = useRef<HTMLDivElement>(null)
  const { pulling, refreshing, progress } = usePullToRefresh(ref, onRefresh)
  const interactive = Boolean(onRefresh)
  const visible = pulling || refreshing

  return (
    <div
      ref={ref}
      className="bg-blobs"
      style={interactive ? { pointerEvents: 'auto' } : undefined}
    >
      <div className="blob blob-1" />
      <div className="blob blob-2" />
      {interactive && (
        <div
          className="pull-logo"
          style={{
            opacity: visible ? Math.min(progress, 1) : 0,
            transform: `translate(-50%, -50%) scale(${0.7 + Math.min(progress, 1) * 0.3})`,
          }}
        >
          <div
            className={refreshing ? 'pull-logo-mark pull-logo-mark--spin' : 'pull-logo-mark'}
            style={
              refreshing
                ? undefined
                : { transform: `rotate(${progress * 360}deg)` }
            }
          >
            N
          </div>
        </div>
      )}
    </div>
  )
}
