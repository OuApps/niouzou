import { useState } from 'react'
import { Pencil, Check, SlidersHorizontal } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { EmptyState } from '../components/EmptyState'
import { MOCK_KEYWORDS } from '../mocks/articles'
import type { KeywordWeight } from '../types/api'

export const Keywords = () => {
  const [keywords, setKeywords] = useState<KeywordWeight[]>(MOCK_KEYWORDS)
  const [editingTerm, setEditingTerm] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const positive = keywords.filter((k) => k.weight > 0).sort((a, b) => b.weight - a.weight)
  const negative = keywords.filter((k) => k.weight < 0).sort((a, b) => a.weight - b.weight)
  const maxAbsWeight = Math.max(...keywords.map((k) => Math.abs(k.weight)), 1)

  const startEdit = (kw: KeywordWeight) => {
    setEditingTerm(kw.term)
    setEditValue(String(kw.weight))
  }

  const confirmEdit = () => {
    if (editingTerm === null) return
    const newWeight = parseFloat(editValue)
    if (isNaN(newWeight)) {
      setEditingTerm(null)
      return
    }
    setKeywords((prev) =>
      prev.map((k) => (k.term === editingTerm ? { ...k, weight: newWeight } : k)),
    )
    setEditingTerm(null)
  }

  const renderRow = (kw: KeywordWeight) => {
    const isEditing = editingTerm === kw.term
    const barWidth = (Math.abs(kw.weight) / maxAbsWeight) * 50
    const isPositive = kw.weight >= 0

    return (
      <div
        key={kw.term}
        className="glass-sm"
        style={{
          borderRadius: 16,
          padding: '12px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        {/* Term */}
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            width: 90,
            flexShrink: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {kw.term}
        </span>

        {/* Bar */}
        <div className="flex-1" style={{ height: 8, position: 'relative' }}>
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: '50%',
              width: 1,
              height: '100%',
              background: 'var(--divider)',
            }}
          />
          <div
            style={{
              position: 'absolute',
              top: 0,
              height: '100%',
              borderRadius: 4,
              ...(isPositive
                ? {
                    left: '50%',
                    width: `${barWidth}%`,
                    background: 'var(--action-like)',
                  }
                : {
                    right: '50%',
                    width: `${barWidth}%`,
                    background: 'var(--action-dislike)',
                  }),
            }}
          />
        </div>

        {/* Counts */}
        <div
          style={{ fontSize: 10, color: 'var(--text-tertiary)', width: 50, textAlign: 'center', flexShrink: 0 }}
        >
          +{kw.like_count} / -{kw.dislike_count}
        </div>

        {/* Edit */}
        {isEditing ? (
          <div className="flex items-center gap-1" style={{ flexShrink: 0 }}>
            <input
              type="number"
              step="0.1"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && confirmEdit()}
              autoFocus
              style={{
                width: 52,
                padding: '4px 6px',
                borderRadius: 8,
                border: '1px solid var(--accent-border)',
                background: 'rgba(255,255,255,0.05)',
                color: 'var(--text-primary)',
                fontSize: 12,
                outline: 'none',
              }}
            />
            <button
              onClick={confirmEdit}
              style={{
                background: 'none',
                border: 'none',
                padding: 4,
                cursor: 'pointer',
                color: 'var(--accent)',
              }}
            >
              <Check size={16} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => startEdit(kw)}
            aria-label={`Edit ${kw.term}`}
            style={{
              background: 'none',
              border: 'none',
              padding: 4,
              cursor: 'pointer',
              color: 'var(--text-tertiary)',
              flexShrink: 0,
            }}
          >
            <Pencil size={14} />
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col min-h-dvh relative">
      <BlobBackground />

      <header
        className="relative z-10 flex items-center justify-center"
        style={{ padding: '16px 20px 8px' }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Keywords
        </h1>
      </header>

      <div className="relative z-10 flex-1" style={{ padding: '8px 16px 90px' }}>
        {keywords.length === 0 ? (
          <EmptyState
            icon={SlidersHorizontal}
            title="No keywords yet"
            description="As you swipe articles, the system will learn your keyword preferences."
          />
        ) : (
          <>
            {positive.length > 0 && (
              <>
                <h4
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.8px',
                    color: 'var(--action-like)',
                    margin: '12px 0 8px 4px',
                  }}
                >
                  Positive
                </h4>
                <div className="flex flex-col gap-2">
                  {positive.map(renderRow)}
                </div>
              </>
            )}
            {negative.length > 0 && (
              <>
                <h4
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.8px',
                    color: 'var(--action-dislike)',
                    margin: '20px 0 8px 4px',
                  }}
                >
                  Negative
                </h4>
                <div className="flex flex-col gap-2">
                  {negative.map(renderRow)}
                </div>
              </>
            )}
          </>
        )}
      </div>

      <BottomNav />
    </div>
  )
}
