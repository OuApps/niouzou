import { useCallback, useEffect, useRef, useState } from 'react'
import { Pencil, Check, SlidersHorizontal, Lock, LockOpen, Trash2 } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { getKeywords, patchKeyword, resetKeywords, ApiError } from '../api'
import type { KeywordWeight } from '../types/api'

const PAGE_SIZE = 50

interface Override {
  weight?: number
  manually_overridden?: boolean
}

export const Keywords = () => {
  const [keywords, setKeywords] = useState<KeywordWeight[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)

  const [editingTerm, setEditingTerm] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [saving, setSaving] = useState(false)
  // Optimistic overrides layered over the fetched list.
  const [overrides, setOverrides] = useState<Record<string, Override>>({})

  const [confirmReset, setConfirmReset] = useState(false)
  const [resetting, setResetting] = useState(false)

  // ── Initial load + reload ─────────────────────────────────────────────────
  useEffect(() => {
    let active = true
    setStatus('loading')
    getKeywords(undefined, PAGE_SIZE)
      .then((page) => {
        if (!active) return
        setKeywords(page.keywords)
        setCursor(page.next_cursor)
        setHasMore(page.has_more)
        setOverrides({})
        setStatus('ready')
      })
      .catch((e) => {
        if (!active) return
        setErrorMsg(e instanceof ApiError ? e.message : 'Something went wrong.')
        setStatus('error')
      })
    return () => {
      active = false
    }
  }, [reloadKey])

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore || !cursor) return
    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const page = await getKeywords(cursor, PAGE_SIZE)
      setKeywords((prev) => [...prev, ...page.keywords])
      setCursor(page.next_cursor)
      setHasMore(page.has_more)
    } catch {
      // Silent — user can keep editing what's loaded.
    } finally {
      loadingMoreRef.current = false
      setLoadingMore(false)
    }
  }, [cursor, hasMore])

  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinelRef.current
    if (!node || !hasMore || status !== 'ready') return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadMore()
      },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasMore, status, loadMore])

  // ── Editing ───────────────────────────────────────────────────────────────
  const startEdit = (kw: KeywordWeight) => {
    setEditingTerm(kw.term)
    setEditValue(String(kw.weight))
  }

  const confirmEdit = async () => {
    if (editingTerm === null) return
    const term = editingTerm
    const newWeight = parseFloat(editValue)
    if (isNaN(newWeight)) {
      setEditingTerm(null)
      return
    }
    setOverrides((prev) => ({
      ...prev,
      [term]: { weight: newWeight, manually_overridden: true },
    }))
    setEditingTerm(null)
    setSaving(true)
    try {
      const updated = await patchKeyword(term, { weight: newWeight })
      setOverrides((prev) => ({
        ...prev,
        [term]: {
          weight: updated.weight,
          manually_overridden: updated.manually_overridden,
        },
      }))
    } catch {
      // Revert optimistic override on failure.
      setOverrides((prev) => {
        const rest = { ...prev }
        delete rest[term]
        return rest
      })
    } finally {
      setSaving(false)
    }
  }

  const clearPin = async (term: string) => {
    // Optimistic: drop the lock badge immediately.
    setOverrides((prev) => ({
      ...prev,
      [term]: { ...(prev[term] ?? {}), manually_overridden: false },
    }))
    try {
      const updated = await patchKeyword(term, { manually_overridden: false })
      setOverrides((prev) => ({
        ...prev,
        [term]: {
          weight: updated.weight,
          manually_overridden: updated.manually_overridden,
        },
      }))
    } catch {
      // Revert: put the lock back.
      setOverrides((prev) => ({
        ...prev,
        [term]: { ...(prev[term] ?? {}), manually_overridden: true },
      }))
    }
  }

  const doReset = async () => {
    setResetting(true)
    try {
      await resetKeywords()
      setKeywords([])
      setCursor(null)
      setHasMore(false)
      setOverrides({})
      setConfirmReset(false)
    } catch {
      // Surface as inline error; keep modal open.
      setErrorMsg('Reset failed. Please try again.')
    } finally {
      setResetting(false)
    }
  }

  // ── Derived view ──────────────────────────────────────────────────────────
  const merged: KeywordWeight[] = keywords.map((k) => {
    const o = overrides[k.term]
    if (!o) return k
    return {
      ...k,
      ...(o.weight !== undefined ? { weight: o.weight } : {}),
      ...(o.manually_overridden !== undefined
        ? { manually_overridden: o.manually_overridden }
        : {}),
    }
  })

  const positive = merged.filter((k) => k.weight > 0).sort((a, b) => b.weight - a.weight)
  const negative = merged.filter((k) => k.weight < 0).sort((a, b) => a.weight - b.weight)
  const maxAbsWeight = Math.max(...merged.map((k) => Math.abs(k.weight)), 1)

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
        {/* Term + lock indicator. flex-basis caps the natural width but
            wrapping is allowed so long keywords aren't ellipsised away. */}
        <span
          title={kw.term}
          style={{
            fontSize: 13,
            fontWeight: 600,
            flex: '0 1 110px',
            minWidth: 0,
            wordBreak: 'break-word',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <span style={{ minWidth: 0 }}>{kw.term}</span>
          {kw.manually_overridden && (
            <Lock
              size={11}
              style={{ color: 'var(--accent-text)', flexShrink: 0 }}
              aria-label="Manually pinned"
            />
          )}
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

        {/* Unlock (only when pinned) */}
        {kw.manually_overridden && !isEditing && (
          <button
            onClick={() => clearPin(kw.term)}
            aria-label={`Unlock ${kw.term}`}
            title="Unpin — let the cron recompute this weight"
            style={{
              background: 'none',
              border: 'none',
              padding: 4,
              cursor: 'pointer',
              color: 'var(--text-tertiary)',
              flexShrink: 0,
            }}
          >
            <LockOpen size={14} />
          </button>
        )}

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
              disabled={saving}
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
      <BlobBackground onRefresh={reload} />

      <header
        className="relative z-10 flex items-center justify-between"
        style={{ padding: '16px 20px 8px' }}
      >
        <span style={{ width: 24 }} />
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Keywords
        </h1>
        {keywords.length > 0 ? (
          <button
            onClick={() => setConfirmReset(true)}
            aria-label="Reset all keywords"
            title="Reset all keywords"
            style={{
              background: 'none',
              border: 'none',
              padding: 4,
              cursor: 'pointer',
              color: 'var(--text-tertiary)',
            }}
          >
            <Trash2 size={18} />
          </button>
        ) : (
          <span style={{ width: 24 }} />
        )}
      </header>

      <div
        className="relative z-10 flex-1"
        style={{
          padding: '8px 16px calc(env(safe-area-inset-bottom, 0px) + 110px)',
        }}
      >
        {status === 'loading' ? (
          <div className="flex justify-center" style={{ paddingTop: 60 }}>
            <Spinner size={30} />
          </div>
        ) : status === 'error' ? (
          <ErrorState message={errorMsg} onRetry={reload} />
        ) : merged.length === 0 ? (
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
            {hasMore && (
              <div
                ref={sentinelRef}
                className="flex justify-center"
                style={{ padding: '16px 0 0' }}
              >
                {loadingMore && <Spinner size={22} />}
              </div>
            )}
          </>
        )}
      </div>

      {/* Reset-all confirmation modal */}
      {confirmReset && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => !resetting && setConfirmReset(false)}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 50,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 20,
          }}
        >
          <div
            className="glass"
            onClick={(e) => e.stopPropagation()}
            style={{
              borderRadius: 20,
              padding: 20,
              maxWidth: 320,
              width: '100%',
              background: 'var(--bg-elevated, rgba(20,24,34,0.95))',
            }}
          >
            <h3
              style={{
                fontSize: 16,
                fontWeight: 600,
                margin: '0 0 8px',
                color: 'var(--text-primary)',
              }}
            >
              Reset all keywords?
            </h3>
            <p
              style={{
                fontSize: 13,
                lineHeight: 1.5,
                color: 'var(--text-secondary)',
                margin: '0 0 16px',
              }}
            >
              This will delete all your keyword weights. This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmReset(false)}
                disabled={resetting}
                style={{
                  padding: '8px 14px',
                  borderRadius: 10,
                  border: '1px solid var(--divider)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={doReset}
                disabled={resetting}
                style={{
                  padding: '8px 14px',
                  borderRadius: 10,
                  border: 'none',
                  background: 'var(--action-dislike)',
                  color: '#fff',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  opacity: resetting ? 0.7 : 1,
                }}
              >
                {resetting ? 'Resetting…' : 'Reset all'}
              </button>
            </div>
          </div>
        </div>
      )}

      <BottomNav />
    </div>
  )
}
