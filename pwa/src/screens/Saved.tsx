import { useNavigate } from 'react-router-dom'
import { Bookmark } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ScoreBadge } from '../components/ScoreBadge'
import { EmptyState } from '../components/EmptyState'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { MOCK_ARTICLES } from '../mocks/articles'
import { useFeedbackStore } from '../store/feedback'

export const Saved = () => {
  const navigate = useNavigate()
  const feedbacks = useFeedbackStore((s) => s.feedbacks)

  const articles = MOCK_ARTICLES.filter((a) => feedbacks[a.id] === 'save')

  return (
    <div className="flex flex-col min-h-dvh relative">
      <BlobBackground />

      <header
        className="relative z-10 flex items-center justify-center"
        style={{ padding: '16px 20px 8px' }}
      >
        <h1 style={{ fontSize: 19, fontWeight: 600, color: 'var(--text-primary)' }}>
          Saved
        </h1>
      </header>

      <div className="relative z-10 flex-1" style={{ padding: '8px 16px 90px' }}>
        {articles.length === 0 ? (
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
