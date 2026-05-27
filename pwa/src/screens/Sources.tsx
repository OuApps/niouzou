import { useState } from 'react'
import { ArrowLeft, Trash2, Plus, Rss } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { EmptyState } from '../components/EmptyState'
import { MOCK_SOURCES } from '../mocks/articles'
import type { SourceFull } from '../types/api'

export const Sources = () => {
  const navigate = useNavigate()
  const [sources, setSources] = useState<SourceFull[]>(MOCK_SOURCES)
  const [newUrl, setNewUrl] = useState('')
  const [urlError, setUrlError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const handleAdd = () => {
    setUrlError('')
    if (!newUrl.startsWith('http')) {
      setUrlError('URL must start with http')
      return
    }
    if (sources.some((s) => s.url === newUrl)) {
      setUrlError('Source already exists')
      return
    }
    const newSource: SourceFull = {
      id: `s${Date.now()}`,
      name: new URL(newUrl).hostname.replace('www.', ''),
      url: newUrl,
      created_at: new Date().toISOString(),
    }
    setSources((prev) => [...prev, newSource])
    setNewUrl('')
  }

  const handleDelete = (id: string) => {
    if (confirmDelete === id) {
      setSources((prev) => prev.filter((s) => s.id !== id))
      setConfirmDelete(null)
    } else {
      setConfirmDelete(id)
    }
  }

  return (
    <div className="flex flex-col min-h-dvh relative">
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
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
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
              style={{
                padding: '10px 14px',
                borderRadius: 10,
                background: 'var(--accent)',
                color: '#0c1018',
                border: 'none',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <Plus size={16} />
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
        {sources.length === 0 ? (
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
                className="glass-sm flex items-center gap-3"
                style={{ borderRadius: 16, padding: '12px 14px' }}
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
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
