import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { getScoreDebug } from '../api'
import type { ScoreDebug } from '../api'
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
 */
export const ScoreDebugSheet = ({ articleId, onClose }: Props) => {
  const [data, setData] = useState<ScoreDebug | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!articleId) {
      setData(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getScoreDebug(articleId)
      .then((debug) => {
        if (!cancelled) setData(debug)
      })
      .catch(() => {
        if (!cancelled) setError('Could not load score details.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
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

const ScoreDebugContent = ({ debug }: { debug: ScoreDebug }) => {
  const pct =
    debug.relevance_score !== null
      ? `${Math.round(debug.relevance_score * 100)}%`
      : '—'
  const scorerLabel =
    debug.scorer === 'ai_keyword'
      ? 'AI'
      : debug.scorer === 'tfidf'
        ? 'TF-IDF'
        : '—'
  return (
    <>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          marginBottom: 16,
          fontSize: 12,
          color: 'var(--text-secondary)',
        }}
      >
        <span>
          Score <strong style={{ color: 'var(--text-primary)' }}>{pct}</strong>
        </span>
        <span>·</span>
        <span>{scorerLabel}</span>
        {debug.enrichment_model && (
          <>
            <span>·</span>
            <span style={{ fontFamily: 'monospace', fontSize: 11 }}>
              {debug.enrichment_model}
            </span>
          </>
        )}
      </div>

      {debug.keywords.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
          No keywords extracted for this article.
        </div>
      ) : (
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
      )}
    </>
  )
}
