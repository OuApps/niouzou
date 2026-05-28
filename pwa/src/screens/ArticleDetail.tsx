import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ThumbsUp, ThumbsDown, Bookmark, BookmarkCheck, ExternalLink } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { ScoreBadge } from '../components/ScoreBadge'
import { KeywordTag } from '../components/KeywordTag'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { useApiData } from '../hooks/useApiData'
import { useFeedbackStore } from '../store/feedback'
import { getArticle, postFeedback } from '../api'
import type { FeedArticle, FeedbackAction } from '../types/api'

export const ArticleDetail = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: article, loading, error, reload } = useApiData(() => getArticle(id!), [id])

  const storeFeedbacks = useFeedbackStore((s) => s.feedbacks)
  const setFeedback = useFeedbackStore((s) => s.setFeedback)

  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Current action, derived: this session's optimistic store overlay wins over
  // the server value — no effect, no duplicated state.
  const override = id ? storeFeedbacks[id] : undefined
  const action: FeedbackAction | null = override ?? article?.feedback?.action ?? null

  const apply = async (next: FeedbackAction) => {
    if (!id || submitting) return
    setSubmitError(null)
    // Stash a FeedArticle-shaped projection when saving so the Saved screen
    // can show it immediately (E7-S11). Other actions just clear the stash.
    const asFeedArticle: FeedArticle | undefined =
      next === 'save' && article
        ? {
            id: article.id,
            title: article.title,
            summary_short: article.summary_short ?? '',
            og_image_url: article.og_image_url,
            url: article.url,
            source: { id: article.source.id, name: article.source.name },
            published_at: article.published_at ?? '',
            relevance_score: article.relevance_score ?? 0,
            scorer: article.scorer,
            keywords: article.keywords ?? [],
          }
        : undefined
    setFeedback(id, next, asFeedArticle)
    setSubmitting(true)
    try {
      await postFeedback(id, next)
      // Like/dislike from detail: return to the previous screen so the user
      // can keep swiping without an extra tap. Save keeps them on the article.
      if (next === 'like' || next === 'dislike') {
        navigate(-1)
        return
      }
    } catch {
      setSubmitError("Couldn't save your feedback. Please try again.")
    } finally {
      setSubmitting(false)
    }
  }

  const toggleSave = () => {
    if (!id) return
    // No unsave endpoint — 'skip' is the neutral action that drops it from /saved.
    apply(action === 'save' ? 'skip' : 'save')
  }

  if (loading) {
    return (
      <div className="h-dvh overflow-y-auto relative">
        <BlobBackground />
        <div className="relative z-10 flex items-center justify-center" style={{ minHeight: '100dvh' }}>
          <Spinner size={32} />
        </div>
      </div>
    )
  }

  if (error || !article) {
    return (
      <div className="h-dvh overflow-y-auto relative">
        <BlobBackground />
        <button
          onClick={() => navigate(-1)}
          aria-label="Back"
          style={{
            position: 'absolute',
            top: 'calc(env(safe-area-inset-top, 0px) + 12px)',
            left: 12,
            zIndex: 20,
            background: 'rgba(12, 16, 24, 0.6)',
            backdropFilter: 'blur(8px)',
            border: 'none',
            borderRadius: '50%',
            width: 36,
            height: 36,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-primary)',
            cursor: 'pointer',
          }}
        >
          <ArrowLeft size={18} />
        </button>
        <div className="relative z-10 flex items-center justify-center" style={{ minHeight: '100dvh' }}>
          <ErrorState message={error ?? 'Article not found'} onRetry={reload} />
        </div>
      </div>
    )
  }

  const isSaved = action === 'save'

  const bullets = article.summary_executive
    ? article.summary_executive
        .split('\n')
        .map((l) => l.replace(/^-\s*/, '').trim())
        .filter(Boolean)
    : null

  return (
    <div className="h-dvh overflow-y-auto relative">
      <BlobBackground />

      {/* Header image */}
      <div className="relative z-10" style={{ height: 220, overflow: 'hidden' }}>
        {article.og_image_url ? (
          <img
            src={article.og_image_url}
            alt=""
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              background: 'linear-gradient(135deg, rgba(244,162,97,0.3), rgba(72,202,228,0.3))',
            }}
          />
        )}
        {/* Gradient overlay */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(transparent 40%, var(--bg-base) 100%)',
          }}
        />
        {/* Back button */}
        <button
          onClick={() => navigate(-1)}
          aria-label="Back"
          style={{
            position: 'absolute',
            top: 'calc(env(safe-area-inset-top, 0px) + 12px)',
            left: 12,
            background: 'rgba(12, 16, 24, 0.6)',
            backdropFilter: 'blur(8px)',
            border: 'none',
            borderRadius: '50%',
            width: 36,
            height: 36,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-primary)',
            cursor: 'pointer',
          }}
        >
          <ArrowLeft size={18} />
        </button>
        {/* Score badge */}
        <div style={{ position: 'absolute', top: 'calc(env(safe-area-inset-top, 0px) + 12px)', right: 12 }}>
          <ScoreBadge score={article.relevance_score} scorer={article.scorer} />
        </div>
      </div>

      {/* Content */}
      <div className="relative z-10" style={{ padding: '0 20px 100px', marginTop: -20 }}>
        {/* Source + date */}
        <div
          className="flex items-center gap-2"
          style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 10 }}
        >
          <span style={{ fontWeight: 600, color: 'var(--accent-text)' }}>{article.source.name}</span>
          <span>·</span>
          <span>{formatTimeAgo(article.published_at)}</span>
        </div>

        <h1
          style={{
            fontSize: 20,
            fontWeight: 600,
            lineHeight: 1.35,
            margin: '0 0 16px',
          }}
        >
          {article.title}
        </h1>

        {/* Executive summary */}
        {bullets && (
          <div
            className="glass-sm"
            style={{ borderRadius: 16, padding: '14px 16px', marginBottom: 16 }}
          >
            <h4
              style={{
                fontSize: 11,
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.8px',
                color: 'var(--accent-text)',
                margin: '0 0 10px',
              }}
            >
              Key takeaways
            </h4>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {bullets.map((b, i) => (
                <li
                  key={i}
                  style={{
                    fontSize: 12,
                    lineHeight: 1.6,
                    color: 'var(--text-secondary)',
                    marginBottom: 6,
                  }}
                >
                  {b}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Summary */}
        <p
          style={{
            fontSize: 13,
            lineHeight: 1.65,
            color: 'var(--text-secondary)',
            marginBottom: 16,
          }}
        >
          {article.summary_short}
        </p>

        {/* Keywords — scrollable row so long lists don't break the layout. */}
        {article.keywords && article.keywords.length > 0 && (
          <div
            className="flex gap-1.5"
            style={{
              marginBottom: 20,
              overflowX: 'auto',
              flexWrap: 'nowrap',
              scrollbarWidth: 'none',
              paddingBottom: 2,
            }}
          >
            {article.keywords.map((kw) => (
              <span key={kw} style={{ flexShrink: 0 }}>
                <KeywordTag term={kw} />
              </span>
            ))}
          </div>
        )}

        {/* Read full article */}
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2"
          style={{
            display: 'flex',
            width: '100%',
            padding: '14px 0',
            borderRadius: 16,
            background: 'var(--accent)',
            color: '#0c1018',
            fontSize: 14,
            fontWeight: 600,
            textDecoration: 'none',
            marginBottom: 16,
          }}
        >
          Read full article
          <ExternalLink size={16} />
        </a>

        {submitError && (
          <div
            role="alert"
            style={{
              fontSize: 12,
              color: 'var(--action-dislike)',
              textAlign: 'center',
              marginBottom: 12,
            }}
          >
            {submitError}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-center items-center gap-8">
          <button
            onClick={() => apply('dislike')}
            aria-label="Dislike"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: action === 'dislike' ? 'var(--action-dislike)' : 'var(--text-secondary)',
            }}
          >
            <ThumbsDown size={24} />
          </button>
          <button
            onClick={toggleSave}
            aria-label={isSaved ? 'Unsave' : 'Save'}
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: isSaved ? 'var(--action-save)' : 'var(--text-secondary)',
            }}
          >
            {isSaved ? <BookmarkCheck size={24} /> : <Bookmark size={24} />}
          </button>
          <button
            onClick={() => apply('like')}
            aria-label="Like"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: action === 'like' ? 'var(--action-like)' : 'var(--text-secondary)',
            }}
          >
            <ThumbsUp size={24} />
          </button>
        </div>
      </div>
    </div>
  )
}
