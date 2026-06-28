import { useEffect, useState } from 'react'
import { Hash, Lock, Radar, X } from 'lucide-react'
import { getScoreDebug } from '../api'
import type { ScoreDebug, ScoreDebugNeighbor } from '../api'
import { Spinner } from './Spinner'

interface Props {
  articleId: string | null
  onClose: () => void
}

/**
 * E10-S2 — Bottom sheet that explains how an article's relevance score was
 * computed. Triggered by tapping the score badge on a feed/explore/saved
 * card. Fetches on open and caches nothing — score debug is rarely opened
 * twice on the same article.
 *
 * E16-S10 — both methods are always shown side by side: the keyword section
 * (article keywords × learned weights) and the Smart Match section (k-NN
 * neighbours + pinned boost), each with its own percentage. The active one
 * (driving the feed) is tagged.
 */
export const ScoreDebugSheet = ({ articleId, onClose }: Props) => {
  const [data, setData] = useState<ScoreDebug | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!articleId) {
        setData(null)
        setError(null)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const debug = await getScoreDebug(articleId)
        if (!cancelled) setData(debug)
      } catch {
        if (!cancelled) setError('Could not load score details.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [articleId])

  if (!articleId) return null

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 50,
        display: 'flex',
        // Centred modal — the previous bottom-sheet variant felt off-balance
        // on tablet widths and on screens with a small content surface.
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="glass"
        style={{
          width: '100%',
          maxWidth: 520,
          borderRadius: 20,
          // Solid dark background — ``.glass`` already paints 92% opaque,
          // but Safari's backdrop-filter can briefly fall back to the raw
          // rgba which still felt see-through on a busy feed slide. Add
          // an explicit opaque layer so the sheet is always legible.
          background: 'rgba(12, 16, 24, 0.98)',
          padding: '18px 18px 20px',
          color: 'var(--text-primary)',
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
      >
        <div
          className="flex items-center justify-between"
          style={{ marginBottom: 14 }}
        >
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            Score breakdown
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-tertiary)',
              cursor: 'pointer',
              padding: 4,
            }}
          >
            <X size={18} />
          </button>
        </div>

        {loading && (
          <div style={{ padding: 24, display: 'flex', justifyContent: 'center' }}>
            <Spinner size={18} />
          </div>
        )}
        {error && (
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            {error}
          </div>
        )}
        {data && (
          <ScoreDebugContent debug={data} />
        )}
      </div>
    </div>
  )
}

const pctLabel = (score: number | null, coldStart: boolean): string =>
  score === null || coldStart ? '–' : `${Math.round(score * 100)}%`

const ScoreDebugContent = ({ debug }: { debug: ScoreDebug }) => (
  <>
    {debug.enrichment_model && (
      <div
        style={{
          marginBottom: 4,
          fontSize: 11,
          color: 'var(--text-secondary)',
          fontFamily: 'monospace',
        }}
      >
        {debug.enrichment_model}
      </div>
    )}

    <MethodHeader
      Icon={Hash}
      label="Keyword"
      pct={pctLabel(debug.keyword_score, debug.keyword_cold_start)}
      active={debug.active_method === 'keyword'}
    />
    <KeywordSection debug={debug} />

    <MethodHeader
      Icon={Radar}
      label="Smart Match"
      pct={pctLabel(debug.smart_score, debug.smart_cold_start)}
      active={debug.active_method === 'smart'}
    />
    <SmartSection debug={debug} />
  </>
)

// ── Section headers ──────────────────────────────────────────────────────────

const MethodHeader = ({
  Icon,
  label,
  pct,
  active,
}: {
  Icon: typeof Hash
  label: string
  pct: string
  active: boolean
}) => (
  <div
    className="flex items-center justify-between"
    style={{ margin: '14px 0 8px' }}
  >
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 12,
        fontWeight: 600,
        color: 'var(--text-primary)',
      }}
    >
      <Icon size={12} style={{ color: 'var(--accent-text)' }} />
      {label}
      <strong style={{ fontVariantNumeric: 'tabular-nums' }}>{pct}</strong>
      {active && (
        <span
          style={{
            fontSize: 9,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.6px',
            padding: '2px 6px',
            borderRadius: 10,
            background: 'var(--accent-subtle)',
            color: 'var(--accent)',
            border: '1px solid var(--accent)',
          }}
        >
          active
        </span>
      )}
    </span>
  </div>
)

// ── Keyword method — article keywords × learned weights ─────────────────────

const KeywordSection = ({ debug }: { debug: ScoreDebug }) => {
  if (debug.keywords.length === 0) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
        No keywords extracted for this article.
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {debug.keywords.map((kw) => (
        <div
          key={kw.term}
          className="flex items-center justify-between"
          style={{
            padding: '8px 10px',
            borderRadius: 10,
            background: 'rgba(255,255,255,0.04)',
            fontSize: 13,
          }}
        >
          <span style={{ color: 'var(--text-primary)' }}>{kw.term}</span>
          <span
            style={{
              color:
                kw.weight === null
                  ? 'var(--text-tertiary)'
                  : kw.weight > 0
                    ? 'var(--action-like)'
                    : kw.weight < 0
                      ? 'var(--action-dislike)'
                      : 'var(--text-secondary)',
              fontVariantNumeric: 'tabular-nums',
              fontWeight: 600,
            }}
          >
            {kw.weight === null
              ? '—'
              : `${kw.weight > 0 ? '+' : ''}${kw.weight.toFixed(2)}`}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Smart Match method — k-NN neighbours + pinned boost (E16-S7) ─────────────

const sectionTitle = (color: string): React.CSSProperties => ({
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.8px',
  color,
  margin: '10px 0 6px 2px',
})

const NeighborRows = ({
  neighbors,
  sign,
}: {
  neighbors: ScoreDebugNeighbor[]
  sign: 1 | -1
}) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    {neighbors.map((n, i) => (
      <div
        key={`${n.title}-${i}`}
        className="flex items-center justify-between"
        style={{
          padding: '8px 10px',
          borderRadius: 10,
          background: 'rgba(255,255,255,0.04)',
          fontSize: 12,
          gap: 10,
        }}
      >
        <span
          style={{
            color: 'var(--text-primary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            minWidth: 0,
          }}
        >
          {n.title}
        </span>
        <span
          style={{
            display: 'flex',
            gap: 8,
            flexShrink: 0,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>
            sim {n.similarity.toFixed(2)}
          </span>
          <span
            style={{
              fontWeight: 600,
              color: sign > 0 ? 'var(--action-like)' : 'var(--action-dislike)',
            }}
          >
            {sign > 0 ? '+' : '−'}
            {n.contribution.toFixed(2)}
          </span>
        </span>
      </div>
    ))}
  </div>
)

const SmartSection = ({ debug }: { debug: ScoreDebug }) => {
  const liked = debug.liked_neighbors ?? []
  const disliked = debug.disliked_neighbors ?? []
  const pins = debug.pins ?? []

  return (
    <>
      {liked.length === 0 && disliked.length === 0 && pins.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
          No feedback history to compare against yet — the score is neutral.
        </div>
      )}

      {liked.length > 0 && (
        <>
          <h4 style={sectionTitle('var(--action-like)')}>
            Closest to your likes
          </h4>
          <NeighborRows neighbors={liked} sign={1} />
        </>
      )}

      {disliked.length > 0 && (
        <>
          <h4 style={sectionTitle('var(--action-dislike)')}>
            Closest to your dislikes
          </h4>
          <NeighborRows neighbors={disliked} sign={-1} />
        </>
      )}

      {pins.length > 0 && (
        <>
          <h4 style={sectionTitle('var(--accent-text)')}>
            <Lock size={10} style={{ display: 'inline', verticalAlign: '-1px' }} />{' '}
            Pinned keywords
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {pins.map((pin) => (
              <div
                key={pin.term}
                className="flex items-center justify-between"
                style={{
                  padding: '8px 10px',
                  borderRadius: 10,
                  background: 'rgba(255,255,255,0.04)',
                  fontSize: 12,
                }}
              >
                <span style={{ color: 'var(--text-primary)' }}>
                  {pin.term}
                  <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>
                    {' '}
                    ({pin.weight > 0 ? '+' : ''}
                    {pin.weight.toFixed(1)} × {pin.salience.toFixed(2)})
                  </span>
                </span>
                <span
                  style={{
                    fontWeight: 600,
                    fontVariantNumeric: 'tabular-nums',
                    color:
                      pin.contribution >= 0
                        ? 'var(--action-like)'
                        : 'var(--action-dislike)',
                  }}
                >
                  {pin.contribution > 0 ? '+' : ''}
                  {pin.contribution.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}
