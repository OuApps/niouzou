import { useState } from 'react'
import { ArrowLeft, Trash2, Plus, Rss, FileText } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { useApiData } from '../hooks/useApiData'
import {
  addSource,
  deleteSource,
  getSources,
  updateSource,
  ApiError,
} from '../api'
import type { SourceFull } from '../types/api'

export const Sources = () => {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useApiData(() => getSources(), [])
  const [newUrl, setNewUrl] = useState('')
  const [urlError, setUrlError] = useState('')
  const [adding, setAdding] = useState(false)
  const [fetchFullContent, setFetchFullContent] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  // Optimistic overlays over the fetched list (no effect copying into state).
  const [added, setAdded] = useState<SourceFull[]>([])
  const [removed, setRemoved] = useState<Set<string>>(new Set())
  // Per-source crawler overrides applied on top of the server payload — lets
  // the toggle reflect immediately without waiting for a refetch.
  const [crawlerOverrides, setCrawlerOverrides] = useState<Record<string, boolean>>({})
  const [togglingId, setTogglingId] = useState<string | null>(null)

  const sources: SourceFull[] = [
    ...(data?.sources ?? []).filter((s) => !removed.has(s.id)),
    ...added.filter((s) => !removed.has(s.id)),
  ].map((s) =>
    s.id in crawlerOverrides
      ? { ...s, fetch_full_content: crawlerOverrides[s.id] }
      : s,
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
      const created = await addSource(url, fetchFullContent)
      setAdded((prev) => [...prev, created])
      setNewUrl('')
      setFetchFullContent(false)
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

  const handleDelete = async (id: string) => {
    if (confirmDelete !== id) {
      setConfirmDelete(id)
      return
    }
    setConfirmDelete(null)
    setRemoved((prev) => new Set(prev).add(id)) // optimistic
    try {
      await deleteSource(id)
      // Also purge from `added` so a source created-then-deleted this session
      // doesn't reappear after a reload (removed keeps filtering server data).
      setAdded((prev) => prev.filter((s) => s.id !== id))
    } catch {
      setRemoved((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      }) // restore on failure
    }
  }

  const handleToggleFullContent = async (source: SourceFull) => {
    const next = !source.fetch_full_content
    setCrawlerOverrides((prev) => ({ ...prev, [source.id]: next }))
    setTogglingId(source.id)
    try {
      await updateSource(source.id, { fetch_full_content: next })
    } catch {
      // Rollback on failure.
      setCrawlerOverrides((prev) => ({
        ...prev,
        [source.id]: source.fetch_full_content,
      }))
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
          <label
            className="flex items-start gap-2"
            style={{ marginTop: 10, cursor: 'pointer', fontSize: 12 }}
          >
            <input
              type="checkbox"
              checked={fetchFullContent}
              onChange={(e) => setFetchFullContent(e.target.checked)}
              style={{ marginTop: 2, accentColor: 'var(--accent)' }}
            />
            <span style={{ color: 'var(--text-secondary)' }}>
              Récupérer l'article complet
              <span
                style={{
                  display: 'block',
                  color: 'var(--text-tertiary)',
                  fontSize: 11,
                  marginTop: 2,
                }}
              >
                Recommandé pour les sites où le flux RSS ne contient qu'un résumé.
              </span>
            </span>
          </label>
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
                className="glass-sm flex flex-col gap-2"
                style={{ borderRadius: 16, padding: '12px 14px' }}
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
                  </div>
                  <button
                    onClick={() => handleDelete(source.id)}
                    aria-label={confirmDelete === source.id ? 'Confirm delete' : `Delete ${source.name}`}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 6,
                      cursor: 'pointer',
                      color: confirmDelete === source.id ? '#f87171' : 'var(--text-tertiary)',
                      flexShrink: 0,
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <FullContentToggle
                  source={source}
                  busy={togglingId === source.id}
                  onToggle={() => handleToggleFullContent(source)}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

interface FullContentToggleProps {
  source: SourceFull
  busy: boolean
  onToggle: () => void
}

const FullContentToggle = ({ source, busy, onToggle }: FullContentToggleProps) => (
  <div
    className="flex items-start gap-2"
    style={{
      paddingTop: 8,
      borderTop: '1px solid var(--divider)',
    }}
  >
    <FileText
      size={12}
      style={{ color: 'var(--text-tertiary)', flexShrink: 0, marginTop: 3 }}
    />
    <div className="flex-1 min-w-0">
      <label
        className="flex items-center justify-between gap-3"
        style={{ cursor: busy ? 'default' : 'pointer', fontSize: 12 }}
      >
        <span style={{ color: 'var(--text-secondary)' }}>
          Récupérer l'article complet
        </span>
        <input
          type="checkbox"
          checked={source.fetch_full_content}
          disabled={busy}
          onChange={onToggle}
          style={{ accentColor: 'var(--accent)' }}
        />
      </label>
      <p
        style={{
          fontSize: 10,
          color: 'var(--text-tertiary)',
          marginTop: 2,
          lineHeight: 1.4,
        }}
      >
        Ce réglage s'applique à tous les utilisateurs abonnés à cette source.
      </p>
    </div>
  </div>
)
