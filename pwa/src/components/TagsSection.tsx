// E24-S8 — "Tags" section on the user Settings (Profile) screen.
// Lifecycle management only: rename, per-tag threshold (percentage, with an
// "inherit" reset to the global SCORE_THRESHOLD) and delete. Attaching tags
// to sources lives on the Sources screen (E24-S6). Per-user — this is NOT an
// admin section; thresholds never transit through /admin/config.

import { useState } from 'react'
import { ChevronDown, ChevronRight, Tag as TagIcon, Trash2 } from 'lucide-react'

import { ApiError, deleteTag, listTags, updateTag } from '../api'
import { useApiData } from '../hooks/useApiData'
import { Spinner } from './Spinner'
import type { Tag } from '../types/api'

export const TagsSection = () => {
  const { data, loading } = useApiData(() => listTags(), [])
  const [open, setOpen] = useState(false)
  // Local working copy so edits/deletes reflect without a refetch. Reset
  // during render when a fresh fetch lands (sanctioned prop-change pattern).
  const [prevData, setPrevData] = useState(data)
  const [items, setItems] = useState<Tag[]>([])
  if (data !== prevData) {
    setPrevData(data)
    setItems(data?.tags ?? [])
  }

  if (loading || items.length === 0) return null

  return (
    <div
      className="glass-sm w-full"
      style={{
        borderRadius: 16,
        border: '1px solid rgba(255,255,255,0.10)',
        background: 'var(--glass-bg)',
      }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-3 w-full"
        style={{
          padding: '14px 16px',
          cursor: 'pointer',
          background: 'none',
          border: 'none',
          color: 'var(--text-primary)',
          fontSize: 14,
        }}
      >
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            background: 'var(--accent-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent)',
          }}
        >
          <TagIcon size={16} />
        </div>
        <span className="flex-1 text-left">
          Tags
          <span
            style={{
              display: 'block',
              fontSize: 11,
              color: 'var(--text-tertiary)',
            }}
          >
            {items.length} tag{items.length === 1 ? '' : 's'} · per-tag feed
            threshold
          </span>
        </span>
        {open ? (
          <ChevronDown size={18} style={{ color: 'var(--text-tertiary)' }} />
        ) : (
          <ChevronRight size={18} style={{ color: 'var(--text-tertiary)' }} />
        )}
      </button>

      {open && (
        <div
          className="flex flex-col"
          style={{ padding: '0 16px 12px', gap: 8 }}
        >
          {items.map((tag) => (
            <TagRow
              key={tag.id}
              tag={tag}
              onChanged={(updated) =>
                setItems((prev) =>
                  prev.map((t) => (t.id === updated.id ? updated : t)),
                )
              }
              onDeleted={() =>
                setItems((prev) => prev.filter((t) => t.id !== tag.id))
              }
            />
          ))}
        </div>
      )}
    </div>
  )
}

const TagRow = ({
  tag,
  onChanged,
  onDeleted,
}: {
  tag: Tag
  onChanged: (tag: Tag) => void
  onDeleted: () => void
}) => {
  const [name, setName] = useState(tag.name)
  // Threshold edited as a whole percentage (parity with the score badge).
  const [pct, setPct] = useState(
    tag.threshold === null ? '' : String(Math.round(tag.threshold * 100)),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const saveName = async () => {
    const trimmed = name.trim()
    if (trimmed === '' || trimmed === tag.name || busy) {
      setName(tag.name)
      return
    }
    setBusy(true)
    setError('')
    try {
      onChanged(await updateTag(tag.id, { name: trimmed }))
    } catch (err) {
      setName(tag.name)
      setError(
        err instanceof ApiError && err.status === 409
          ? 'Name already used'
          : 'Could not rename',
      )
    } finally {
      setBusy(false)
    }
  }

  const saveThreshold = async (raw: string) => {
    if (busy) return
    const current =
      tag.threshold === null ? '' : String(Math.round(tag.threshold * 100))
    if (raw === current) return
    const value = raw === '' ? null : Number(raw) / 100
    if (value !== null && (Number.isNaN(value) || value < 0 || value > 1)) {
      setPct(current)
      return
    }
    setBusy(true)
    setError('')
    try {
      // An empty field means "inherit the global threshold" (null).
      onChanged(await updateTag(tag.id, { threshold: value }))
    } catch {
      setPct(current)
      setError('Could not save threshold')
    } finally {
      setBusy(false)
    }
  }

  const doDelete = async () => {
    setBusy(true)
    setError('')
    try {
      await deleteTag(tag.id)
      onDeleted()
    } catch {
      setError('Could not delete')
      setConfirmDelete(false)
      setBusy(false)
    }
  }

  return (
    <div
      style={{
        borderRadius: 12,
        padding: '8px 10px',
        background: 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <div className="flex items-center" style={{ gap: 8 }}>
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            setError('')
          }}
          onBlur={() => void saveName()}
          onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
          maxLength={40}
          aria-label={`Rename tag ${tag.name}`}
          style={{
            flex: '1 1 auto',
            minWidth: 0,
            border: 'none',
            outline: 'none',
            background: 'transparent',
            color: 'var(--text-primary)',
            fontSize: 13,
            fontWeight: 600,
          }}
        />
        <span
          className="flex items-center"
          style={{ gap: 4, flex: '0 0 auto' }}
        >
          <input
            value={pct}
            onChange={(e) => {
              setPct(e.target.value.replace(/[^0-9]/g, '').slice(0, 3))
              setError('')
            }}
            onBlur={(e) => void saveThreshold(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
            inputMode="numeric"
            placeholder="auto"
            aria-label={`Feed threshold for ${tag.name} (percent)`}
            style={{
              width: 44,
              padding: '4px 6px',
              borderRadius: 8,
              border: '1px solid rgba(255,255,255,0.10)',
              background: 'rgba(255,255,255,0.04)',
              color: 'var(--text-primary)',
              fontSize: 12,
              textAlign: 'right',
              outline: 'none',
            }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>%</span>
          {tag.threshold !== null && (
            <button
              onClick={() => {
                setPct('')
                void saveThreshold('')
              }}
              disabled={busy}
              aria-label={`Inherit the global threshold for ${tag.name}`}
              style={{
                padding: '3px 8px',
                borderRadius: 8,
                border: '1px solid rgba(255,255,255,0.10)',
                background: 'transparent',
                color: 'var(--text-secondary)',
                fontSize: 10,
                cursor: busy ? 'default' : 'pointer',
              }}
            >
              inherit
            </button>
          )}
        </span>
        {busy ? (
          <Spinner size={14} />
        ) : confirmDelete ? (
          <button
            onClick={() => void doDelete()}
            aria-label={`Confirm delete tag ${tag.name}`}
            style={{
              padding: '3px 8px',
              borderRadius: 8,
              border: 'none',
              background: 'var(--action-dislike)',
              color: '#fff',
              fontSize: 10,
              fontWeight: 600,
              cursor: 'pointer',
              flex: '0 0 auto',
            }}
          >
            sure?
          </button>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            aria-label={`Delete tag ${tag.name}`}
            style={{
              background: 'none',
              border: 'none',
              padding: 2,
              color: 'var(--text-tertiary)',
              cursor: 'pointer',
              display: 'flex',
              flex: '0 0 auto',
            }}
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
      <div className="flex items-center" style={{ gap: 8, marginTop: 2 }}>
        <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
          {tag.source_count} source{tag.source_count === 1 ? '' : 's'}
          {tag.threshold === null && ' · inherits global threshold'}
        </span>
        {error && (
          <span style={{ fontSize: 10, color: 'var(--action-dislike)' }}>
            {error}
          </span>
        )}
      </div>
    </div>
  )
}
