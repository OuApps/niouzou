// E24-S6 — inline token-input tag editor on a source card.
// Chips show the source's current tags (tap ✕ to detach); the input attaches
// an existing tag by name or creates one on the fly (POST /tags) then
// attaches it. All mutations go through PUT /sources/{id}/tags
// (set-semantics) so the server list is always the full state.

import { useState } from 'react'
import { Plus, X } from 'lucide-react'

import { ApiError, createTag, setSourceTags } from '../api'
import type { SourceFull, Tag, TagRef } from '../types/api'
import { Spinner } from './Spinner'

interface SourceTagsEditorProps {
  sourceId: string
  tags: TagRef[]
  /** All the user's tags, for suggestions + name → id resolution. */
  allTags: Tag[]
  onSaved: (source: SourceFull) => void
  onTagCreated: (tag: Tag) => void
}

export const SourceTagsEditor = ({
  sourceId,
  tags,
  allTags,
  onSaved,
  onTagCreated,
}: SourceTagsEditorProps) => {
  const [editing, setEditing] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const attachedIds = new Set(tags.map((t) => t.id))
  const query = input.trim().toLowerCase()
  const suggestions = allTags.filter(
    (t) =>
      !attachedIds.has(t.id) &&
      (query === '' || t.name.toLowerCase().includes(query)),
  )
  const exactMatch = allTags.find((t) => t.name.toLowerCase() === query)

  const save = async (tagIds: string[]) => {
    setBusy(true)
    setError('')
    try {
      const updated = await setSourceTags(sourceId, tagIds)
      onSaved(updated)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not update tags.',
      )
    } finally {
      setBusy(false)
    }
  }

  const detach = (tagId: string) =>
    save(tags.filter((t) => t.id !== tagId).map((t) => t.id))

  const attach = (tagId: string) => {
    setInput('')
    return save([...tags.map((t) => t.id), tagId])
  }

  const submit = async () => {
    const name = input.trim()
    if (name === '' || busy) return
    if (exactMatch) {
      await attach(exactMatch.id)
      return
    }
    // Unknown name → create on the fly, then attach.
    setBusy(true)
    setError('')
    try {
      const created = await createTag(name)
      onTagCreated(created)
      setInput('')
      const updated = await setSourceTags(sourceId, [
        ...tags.map((t) => t.id),
        created.id,
      ])
      onSaved(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add tag.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginTop: 6 }}>
      <div className="flex items-center" style={{ flexWrap: 'wrap', gap: 4 }}>
        {tags.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex items-center"
            style={{
              gap: 3,
              padding: '3px 8px',
              borderRadius: 20,
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              fontSize: 10,
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}
          >
            {tag.name}
            <button
              onClick={() => detach(tag.id)}
              disabled={busy}
              aria-label={`Remove tag ${tag.name}`}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                color: 'inherit',
                cursor: busy ? 'default' : 'pointer',
                display: 'flex',
              }}
            >
              <X size={10} />
            </button>
          </span>
        ))}
        {!editing ? (
          <button
            onClick={() => setEditing(true)}
            aria-label="Add a tag"
            className="inline-flex items-center"
            style={{
              gap: 3,
              padding: '3px 8px',
              borderRadius: 20,
              background: 'rgba(255,255,255,0.05)',
              border: '1px dashed rgba(255,255,255,0.15)',
              color: 'var(--text-secondary)',
              fontSize: 10,
              cursor: 'pointer',
            }}
          >
            <Plus size={10} />
            tag
          </button>
        ) : (
          <span className="inline-flex items-center" style={{ gap: 4 }}>
            <input
              autoFocus
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                setError('')
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void submit()
                if (e.key === 'Escape') {
                  setEditing(false)
                  setInput('')
                }
              }}
              onBlur={() => {
                // Keep the row open while a suggestion tap is in flight.
                if (input.trim() === '' && !busy) setEditing(false)
              }}
              placeholder="tag name"
              maxLength={40}
              style={{
                width: 90,
                padding: '3px 8px',
                borderRadius: 20,
                border: '1px solid rgba(255,255,255,0.15)',
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-primary)',
                fontSize: 10,
                outline: 'none',
              }}
            />
            {busy && <Spinner size={10} />}
          </span>
        )}
      </div>
      {editing && suggestions.length > 0 && (
        <div
          className="flex items-center"
          style={{ flexWrap: 'wrap', gap: 4, marginTop: 4 }}
        >
          {suggestions.slice(0, 8).map((tag) => (
            <button
              key={tag.id}
              onMouseDown={(e) => e.preventDefault() /* keep input focus */}
              onClick={() => void attach(tag.id)}
              disabled={busy}
              style={{
                padding: '3px 8px',
                borderRadius: 20,
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.08)',
                color: 'var(--text-secondary)',
                fontSize: 10,
                cursor: busy ? 'default' : 'pointer',
              }}
            >
              {tag.name}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p style={{ fontSize: 10, color: 'var(--action-dislike)', marginTop: 4 }}>
          {error}
        </p>
      )}
    </div>
  )
}
