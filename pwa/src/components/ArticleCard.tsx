import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, Lock } from 'lucide-react'
import { ScoreBadge } from './ScoreBadge'
import { KeywordTag } from './KeywordTag'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import type { FeedArticle } from '../types/api'

interface ArticleCardProps {
  article: FeedArticle
  style?: React.CSSProperties
}

export const ArticleCard = ({ article, style }: ArticleCardProps) => {
  const navigate = useNavigate()
  const [imageLoaded, setImageLoaded] = useState(false)

  return (
    <div
      className="glass"
      style={{
        borderRadius: 28,
        overflow: 'hidden',
        width: '100%',
        maxWidth: 360,
        userSelect: 'none',
        touchAction: 'none',
        ...style,
      }}
    >
      {/* Image */}
      <div style={{ position: 'relative', height: 220, overflow: 'hidden' }}>
        {article.og_image_url ? (
          <>
            {!imageLoaded && (
              <div
                className="skeleton"
                style={{ position: 'absolute', inset: 0 }}
              />
            )}
            <img
              src={article.og_image_url}
              alt=""
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                opacity: imageLoaded ? 1 : 0,
                transition: 'opacity 0.3s ease',
              }}
              draggable={false}
              onLoad={() => setImageLoaded(true)}
            />
          </>
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              background: 'linear-gradient(135deg, rgba(244,162,97,0.3), rgba(72,202,228,0.3))',
            }}
          />
        )}
        <span
          style={{
            position: 'absolute',
            bottom: 10,
            left: 10,
            padding: '4px 10px',
            borderRadius: 20,
            background: 'rgba(12, 16, 24, 0.75)',
            backdropFilter: 'blur(8px)',
            fontSize: 10,
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          {article.source.name}
        </span>
        <div style={{ position: 'absolute', top: 10, right: 10 }}>
          <ScoreBadge score={article.relevance_score} scorer={article.scorer} />
        </div>
        {/* Premium / paywall lock icon — surfaces partial content before the
            user taps the card (E7-S21). */}
        {article.is_premium && (
          <span
            aria-label="Contenu premium"
            title="Contenu partiel — article premium"
            style={{
              position: 'absolute',
              top: 10,
              left: 10,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 26,
              height: 26,
              borderRadius: '50%',
              background: 'rgba(12, 16, 24, 0.75)',
              backdropFilter: 'blur(8px)',
              color: 'var(--accent)',
            }}
          >
            <Lock size={13} />
          </span>
        )}
      </div>

      {/* Content */}
      <div
        style={{ padding: '14px 16px 16px' }}
        onClick={() => navigate(`/articles/${article.id}`)}
      >
        <h3
          style={{
            fontSize: 15,
            fontWeight: 600,
            lineHeight: 1.35,
            margin: '0 0 8px',
            color: 'var(--text-primary)',
          }}
        >
          {article.title}
        </h3>

        <p
          style={{
            fontSize: 12,
            lineHeight: 1.5,
            color: 'var(--text-secondary)',
            margin: '0 0 10px',
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {article.summary_short}
        </p>

        {/* Keywords — top 3 by salience; rest collapsed into "+N". */}
        {article.keywords && article.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1.5" style={{ marginBottom: 10 }}>
            {article.keywords.slice(0, 3).map((kw) => (
              <KeywordTag key={kw} term={kw} />
            ))}
            {article.keywords.length > 3 && (
              <KeywordTag term={`+${article.keywords.length - 3}`} />
            )}
          </div>
        )}

        {/* Meta */}
        <div
          style={{
            borderTop: '1px solid var(--divider)',
            paddingTop: 10,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 10,
            color: 'var(--text-tertiary)',
          }}
        >
          <Clock size={12} />
          <span>{formatTimeAgo(article.published_at)}</span>
          {article.read_time_minutes && (
            <>
              <span>·</span>
              <span>{article.read_time_minutes} min read</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
