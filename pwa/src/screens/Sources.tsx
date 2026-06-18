import { useState } from 'react'
import { ArrowLeft, Plus, Rss } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { useApiData } from '../hooks/useApiData'
import { addSource, getSources, updateSource, ApiError } from '../api'
import type { SourceFull } from '../types/api'

export const Sources = () => {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useApiData(() => getSources(), [])
  const [newUrl, setNewUrl] = useState('')
  const [urlError, setUrlError] = useState('')
  const [adding, setAdding] = useState(false)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  // Optimistic overlays over the fetched list (no effect copying into state).
  const [added, setAdded] = useState<SourceFull[]>([])
  // Per-id active override so a toggle reflects immediately without waiting
  // on a list reload. `undefined` → fall back to server value.
  const [activeOverride, setActiveOverride] = useState<Record<string, boolean>>({})

  const sources: SourceFull[] = [...(data?.sources ?? []), ...added].map((s) =>
    activeOverride[s.id] === undefined
      ? s
      : { ...s, active: activeOverride[s.id] },
  )

  const handleAdd = async () => {
    setUrlError('')
    const url = newUrl.trim()
    if (!url.startsWith('http')) {
      setUrlError('URL must start with http')
      return
    }
    if (sources.some((s) => s.url === url)) {
      setUrlError('Source already exists')
      return
    }
    setAdding(true)
    try {
      // Full-article extraction is always on for new sources — the toggle was
      // removed from the UI; existing sources keep whatever Miniflux had.
      const created = await addSource(url, true)
      setAdded((prev) => [...prev, created])
      setNewUrl('')
    } catch (err) {
      setUrlError(
        err instanceof ApiError && err.status === 409
          ? 'This source already exists'
          : err instanceof ApiError
            ? err.message
            : 'Could not add this source. Please try again.',
      )
    } finally {
      setAdding(false)
    }
  }

  const handleToggleActive = async (source: SourceFull) => {
    const next = !source.active
    setTogglingId(source.id)
    setActiveOverride((prev) => ({ ...prev, [source.id]: next }))
    try {
      await updateSource(source.id, { active: next })
    } catch {
      setActiveOverride((prev) => ({ ...prev, [source.id]: source.active }))
    } finally {
      setTogglingId(null)
    }
  }

  return (
    <div className="flex flex-col h-dvh overflow-y-auto relative">
      <BlobBackground />

      <header
        className="relative z-10 flex items-center"
        style={{ padding: '16px 16px 8px' }}
      >
        <button
          onClick={() => navigate(-1)}
          aria-label="Back"
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-primary)',
            cursor: 'pointer',
            padding: 4,
          }}
        >
          <ArrowLeft size={20} />
        </button>
        <h1
          className="flex-1 text-center"
          style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)', marginRight: 28 }}
        >
          Manage Sources
        </h1>
      </header>

      <div className="relative z-10 flex-1" style={{ padding: '16px 16px 40px' }}>
        {/* Add source */}
        <div className="glass-sm" style={{ borderRadius: 16, padding: 14, marginBottom: 20 }}>
          <div className="flex gap-2">
            <input
              type="url"
              placeholder="https://example.com/feed"
              value={newUrl}
              onChange={(e) => {
                setNewUrl(e.target.value)
                setUrlError('')
              }}
              onKeyDown={(e) => e.key === 'Enter' && !adding && handleAdd()}
              style={{
                flex: 1,
                padding: '10px 12px',
                borderRadius: 10,
                border: urlError ? '1px solid var(--action-dislike)' : '1px solid rgba(255,255,255,0.10)',
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-primary)',
                fontSize: 13,
                outline: 'none',
              }}
            />
            <button
              onClick={handleAdd}
              disabled={adding}
              style={{
                padding: '10px 14px',
                borderRadius: 10,
                background: 'var(--accent)',
                color: '#0c1018',
                border: 'none',
                cursor: adding ? 'default' : 'pointer',
                opacity: adding ? 0.6 : 1,
                fontWeight: 600,
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              {adding ? <Spinner size={14} /> : <Plus size={16} />}
              Add
            </button>
          </div>
          {urlError && (
            <p style={{ fontSize: 11, color: 'var(--action-dislike)', marginTop: 6, paddingLeft: 2 }}>
              {urlError}
            </p>
          )}
        </div>

        {/* Sources list */}
        {loading ? (
          <div className="flex justify-center" style={{ paddingTop: 40 }}>
            <Spinner size={30} />
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : sources.length === 0 ? (
          <EmptyState
            icon={Rss}
            title="No sources"
            description="Add an RSS feed URL above to start following a source."
          />
        ) : (
          <div className="flex flex-col gap-2">
            {sources.map((source) => (
              <div
                key={source.id}
                className="glass-sm"
                style={{
                  borderRadius: 16,
                  padding: '12px 14px',
                  opacity: source.active ? 1 : 0.5,
                  transition: 'opacity 150ms ease',
                }}
              >
                <div className="flex items-center gap-3">
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
                      flexShrink: 0,
                    }}
                  >
                    <Rss size={14} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{source.name}</p>
                    <p
                      style={{
                        fontSize: 10,
                        color: 'var(--text-tertiary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {source.url}
                    </p>
                    {/* E17-S6 — article volume: total + last 24h. */}
                    <p style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                      {source.article_count_total} article{source.article_count_total === 1 ? '' : 's'}
                      {source.article_count_24h > 0 && (
                        <span style={{ color: 'var(--accent-text)' }}>
                          {' · '}+{source.article_count_24h} / 24h
                        </span>
                      )}
                    </p>
                  </div>
                  <label
                    className="flex items-center"
                    style={{
                      cursor: togglingId === source.id ? 'default' : 'pointer',
                      flexShrink: 0,
                    }}
                    aria-label={source.active ? `Pause ${source.name}` : `Resume ${source.name}`}
                  >
                    <input
                      type="checkbox"
                      checked={source.active}
                      disabled={togglingId === source.id}
                      onChange={() => handleToggleActive(source)}
                      style={{ accentColor: 'var(--accent)', width: 16, height: 16 }}
                    />
                  </label>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
