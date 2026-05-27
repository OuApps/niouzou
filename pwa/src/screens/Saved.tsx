import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bookmark } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ScoreBadge } from '../components/ScoreBadge'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { useApiData } from '../hooks/useApiData'
import { useFeedbackStore } from '../store/feedback'
import { getSaved } from '../api'

const PULL_THRESHOLD = 80

export const Saved = () => {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useApiData(() => getSaved(), [])
  // Hide rows the user unsaved this session (no refetch needed).
  const feedbacks = useFeedbackStore((s) => s.feedbacks)

  const articles = (data?.articles ?? []).filter(
    (a) => !(a.id in feedbacks) || feedbacks[a.id] === 'save',
  )

  // Pull-to-refresh
  const [pullY, setPullY] = useState(0)
  const [pulling, setPulling] = useState(false)
  const touchStartY = useRef(0)
  const isPulling = useRef(false)

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
    isPulling.current = false
  }, [])

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    const dy = e.touches[0].clientY - touchStartY.current
    if (dy > 0 && window.scrollY === 0) {
      isPulling.current = true
      setPulling(true)
      setPullY(Math.min(dy * 0.5, 120))
    }
  }, [])

  const onTouchEnd = useCallback(() => {
    if (isPulling.current && pullY > PULL_THRESHOLD) reload()
    setPullY(0)
    setPulling(false)
    isPulling.current = false
  }, [pullY, reload])

  const pullProgress = Math.min(pullY / PULL_THRESHOLD, 1)

  return (
    <div
      className="flex flex-col min-h-dvh relative"
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
    >
      <BlobBackground />

      <div
        className="pull-indicator"
        style={{
          transform: `translateY(${pullY - 40}px)`,
          opacity: pulling ? pullProgress : 0,
        }}
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            transform: `rotate(${pullProgress * 360}deg)`,
            transition: pulling ? 'none' : 'transform 0.3s ease',
          }}
        >
          <path d="M12 2v6" />
          <path d="m9 5 3-3 3 3" />
          <path d="M12 22v-6" />
          <path d="m15 19-3 3-3-3" />
        </svg>
      </div>

      <header
        className="relative z-10 flex items-center justify-center"
        style={{ padding: '16px 20px 8px' }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Saved
        </h1>
      </header>

      <div className="relative z-10 flex-1" style={{ padding: '8px 16px 90px' }}>
        {loading ? (
          <div className="flex justify-center" style={{ paddingTop: 60 }}>
            <Spinner size={30} />
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : articles.length === 0 ? (
          <EmptyState
            icon={Bookmark}
            title="No saved articles"
            description="Articles you save will appear here. Swipe up or tap the bookmark icon to save."
          />
        ) : (
          <div className="flex flex-col gap-3">
            {articles.map((article) => (
              <button
                key={article.id}
                onClick={() => navigate(`/articles/${article.id}`)}
                className="glass-sm flex items-start gap-3 w-full text-left"
                style={{
                  borderRadius: 16,
                  padding: 12,
                  cursor: 'pointer',
                  border: '1px solid rgba(255,255,255,0.10)',
                  background: 'var(--glass-bg)',
                }}
              >
                {article.og_image_url && (
                  <img
                    src={article.og_image_url}
                    alt=""
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: 10,
                      objectFit: 'cover',
                      flexShrink: 0,
                    }}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div
                    className="flex items-center gap-2"
                    style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4 }}
                  >
                    <span>{article.source.name}</span>
                    <ScoreBadge score={article.relevance_score} />
                  </div>
                  <h3
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      lineHeight: 1.35,
                      margin: '0 0 4px',
                      color: 'var(--text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {article.title}
                  </h3>
                  <p style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                    {formatTimeAgo(article.published_at)}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <BottomNav />
    </div>
  )
}
