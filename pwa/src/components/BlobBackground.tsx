import { RefreshCw } from 'lucide-react'
import { usePullToRefresh } from '../hooks/usePullToRefresh'

const REVEAL_OFFSET = 24
const REVEAL_TRAVEL = 56

interface Props {
  /**
   * When provided, the classic top-to-bottom pull gesture on a non-interactive
   * area of the top third triggers this callback (E7-S19). A refresh icon
   * descends from the top with the drag and spins while the returned promise
   * is in flight.
   */
  onRefresh?: () => void | Promise<void>
}

export const BlobBackground = ({ onRefresh }: Props) => {
  const { pulling, refreshing, progress } = usePullToRefresh(onRefresh)
  const interactive = Boolean(onRefresh)
  const visible = pulling || refreshing
  const clamped = Math.min(progress, 1)
  // Slide the indicator down with the gesture so it feels physically pulled.
  const offsetY = visible ? REVEAL_OFFSET + clamped * REVEAL_TRAVEL : 0

  return (
    <>
      <div className="bg-blobs">
        <div className="blob blob-1" />
        <div className="blob blob-2" />
      </div>
      {interactive && (
        <div
          className="pull-indicator-top"
          style={{
            opacity: visible ? clamped : 0,
            transform: `translate(-50%, ${offsetY - 48}px)`,
          }}
        >
          <div
            className={
              refreshing
                ? 'pull-indicator-icon pull-indicator-icon--spin'
                : 'pull-indicator-icon'
            }
            style={
              refreshing ? undefined : { transform: `rotate(${progress * 360}deg)` }
            }
          >
            <RefreshCw size={22} strokeWidth={2.5} />
          </div>
        </div>
      )}
    </>
  )
}
