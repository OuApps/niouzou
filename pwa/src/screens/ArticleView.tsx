import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { FeedArticleSlide } from '../components/FeedArticleSlide'
import { Spinner } from '../components/Spinner'
import { ErrorState } from '../components/ErrorState'
import { diffForPost, useFeedbackStore } from '../store/feedback'
import { useShareArticle } from '../hooks/useShareArticle'
import { getArticleDetail, postFeedback, ApiError } from '../api'
import type { ArticleDetail, FeedbackState, Reaction } from '../types/api'

/**
 * E23-S4 — standalone article view behind the deep link `/article/:id`.
 *
 * Renders any article (shared link, MCP `niouzou_url`) in a single
 * `FeedArticleSlide`. When the article comes from one of the user's own
 * sources (`owned`), scoring + feedback behave like the feed; otherwise it's
 * read-only — displayed, not scored (E23-S3).
 */
export const ArticleView = () => {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { share, toast } = useShareArticle()

  const [article, setArticle] = useState<ArticleDetail | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const applyFeedback = useFeedbackStore((s) => s.apply)
  const removeFeedback = useFeedbackStore((s) => s.remove)
  const getOverlay = useFeedbackStore((s) => s.get)

  useEffect(() => {
    let active = true
    async function load() {
      setStatus('loading')
      try {
        const detail = await getArticleDetail(id)
        if (!active) return
        setArticle(detail)
        setStatus('ready')
      } catch (e) {
        if (!active) return
        if (e instanceof ApiError && e.status === 404) {
          setErrorMsg('Article introuvable.')
        } else {
          setErrorMsg(e instanceof ApiError ? e.message : 'Une erreur est survenue.')
        }
        setStatus('error')
      }
    }
    void load()
    return () => {
      active = false
    }
  }, [id, reloadKey])

  // ── Feedback (owned articles only) — same optimistic pattern as the feed ──
  const send = useCallback(
    (target: ArticleDetail, next: FeedbackState) => {
      const current = getOverlay(target.id, {
        reaction: target.reaction,
        is_saved: target.is_saved,
        read_full_article: target.read_full_article,
      })
      const diff = diffForPost(current, next)
      if (
        diff.reaction === undefined &&
        diff.is_saved === undefined &&
        diff.read_full_article === undefined
      ) {
        return
      }
      applyFeedback(target.id, next, target)
      postFeedback(target.id, diff).catch(() => removeFeedback(target.id))
    },
    [applyFeedback, getOverlay, removeFeedback],
  )

  const onReact = useCallback(
    (target: ArticleDetail, reaction: Reaction) => {
      const current = getOverlay(target.id, {
        reaction: target.reaction,
        is_saved: target.is_saved,
        read_full_article: target.read_full_article,
      })
      send(target, { ...current, reaction })
    },
    [getOverlay, send],
  )

  const onToggleSave = useCallback(
    (target: ArticleDetail) => {
      const current = getOverlay(target.id, {
        reaction: target.reaction,
        is_saved: target.is_saved,
        read_full_article: target.read_full_article,
      })
      send(target, { ...current, is_saved: !current.is_saved })
    },
    [getOverlay, send],
  )

  const onMarkRead = useCallback(
    (target: ArticleDetail) => {
      const current = getOverlay(target.id, {
        reaction: target.reaction,
        is_saved: target.is_saved,
        read_full_article: target.read_full_article,
      })
      if (current.read_full_article) return
      send(target, { ...current, read_full_article: true })
    },
    [getOverlay, send],
  )

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  return (
    <div className="relative" style={{ height: '100dvh', overflow: 'hidden' }}>
      <BlobBackground />

      {status === 'loading' ? (
        <div className="flex justify-center items-center" style={{ height: '100dvh' }}>
          <Spinner size={30} />
        </div>
      ) : status === 'error' ? (
        <div className="relative z-10" style={{ padding: '80px 16px' }}>
          <ErrorState message={errorMsg} onRetry={reload} />
          <button
            type="button"
            onClick={() => navigate('/')}
            className="block mx-auto"
            style={{
              marginTop: 20,
              padding: '10px 16px',
              borderRadius: 20,
              border: '1px solid var(--accent-border)',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Retour au fil
          </button>
        </div>
      ) : article ? (
        <FeedArticleSlide
          article={article}
          standalone
          readOnly={!article.owned}
          onReact={(reaction) => onReact(article, reaction)}
          onToggleSave={() => onToggleSave(article)}
          onMarkRead={() => onMarkRead(article)}
          onShare={() => share(article.id, article.title)}
        />
      ) : null}

      {toast && (
        <div
          role="status"
          className="fixed left-1/2 z-50"
          style={{
            bottom: 'calc(env(safe-area-inset-bottom, 0px) + 90px)',
            transform: 'translateX(-50%)',
            padding: '8px 16px',
            borderRadius: 20,
            background: 'rgba(12,16,24,0.92)',
            border: '1px solid rgba(255,255,255,0.14)',
            color: 'var(--text-primary)',
            fontSize: 13,
            fontWeight: 600,
            backdropFilter: 'blur(10px)',
            WebkitBackdropFilter: 'blur(10px)',
          }}
        >
          {toast}
        </div>
      )}

      <BottomNav />
    </div>
  )
}
