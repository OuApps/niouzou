import { useEffect, useRef, useState } from 'react'
import {
  ThumbsDown,
  ThumbsUp,
  Bookmark,
  ExternalLink,
  Lock,
} from 'lucide-react'
import { ScoreBadge } from './ScoreBadge'
import { KeywordTag } from './KeywordTag'
import { ScrollBoundaryHint } from './ScrollBoundaryHint'
import { formatTimeAgo } from '../hooks/useTimeAgo'
import { useFeedbackStore } from '../store/feedback'
import type { FeedArticle, Reaction } from '../types/api'

interface Props {
  article: FeedArticle
  /** Forwarded to the slide wrapper so the parent IntersectionObserver can track impressions. */
  slideRef?: (el: HTMLElement | null) => void
  /** Forwarded to the *next* slide's wrapper so the chevron stops bouncing when it appears. */
  nextSentinelRef?: (el: HTMLElement | null) => void
  /** Eager-load the og:image for the first two slides; lazy for everyone else. */
  imageEager?: boolean
  /** Fire optimistic feedback. The parent owns the persistence + rollback. */
  onReact: (next: Reaction) => void
  onToggleSave: () => void
  onMarkRead: () => void
}

/**
 * One fullscreen TikTok-like article slide (E9-S2). 100dvh — never `100vh`,
 * which leaves a gap under Safari/Chrome mobile URL bars and clips the action
 * bar. Layout:
 *
 *   [og:image blurred bg + gradients]
 *   ├── sticky header: source badge + score (+ premium lock)
 *   ├── scrollable content: hero image, title, keywords, summaries, content,
 *   │   "Lire l'article" button, ScrollBoundaryHint
 *   └── sticky bottom: dislike / save / like buttons
 */
export const FeedArticleSlide = ({
  article,
  slideRef,
  nextSentinelRef,
  imageEager = false,
  onReact,
  onToggleSave,
  onMarkRead,
}: Props) => {
  // Per-slide subscription: this slide only re-renders when its own overlay
  // changes — not when any other article's feedback flips.
  const override = useFeedbackStore((s) => s.overrides[article.id])
  const state =
    override ?? {
      reaction: article.reaction,
      is_saved: article.is_saved,
      read_full_article: article.read_full_article,
    }
  const slideEl = useRef<HTMLElement | null>(null)
  const nextEl = useRef<HTMLDivElement | null>(null)
  const [nextVisible, setNextVisible] = useState(false)
  const scrollEl = useRef<HTMLDivElement | null>(null)

  // Detect when the next slide enters view so we can stop the chevron bounce.
  useEffect(() => {
    const target = nextEl.current
    if (!target) return
    const observer = new IntersectionObserver(
      (entries) => setNextVisible(entries[0]?.isIntersecting ?? false),
      { threshold: 0.15 },
    )
    observer.observe(target)
    return () => observer.disconnect()
  }, [])

  // Bring the slide back to the top whenever we navigate to it: the snap layout
  // remembers the last scroll position per element, which would skip past the
  // title on re-entry.
  useEffect(() => {
    scrollEl.current?.scrollTo({ top: 0, behavior: 'auto' })
  }, [article.id])

  const handleOpenArticle = () => {
    onMarkRead()
    window.open(article.url, '_blank', 'noopener,noreferrer')
  }

  const liked = state.reaction === 'like'
  const disliked = state.reaction === 'dislike'

  return (
    <article
      ref={(el) => {
        slideEl.current = el
        slideRef?.(el)
      }}
      className="feed-slide"
      data-article-id={article.id}
    >
      {/* Background image, heavily blurred so it acts as ambient colour. */}
      {article.og_image_url && (
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: `url(${article.og_image_url})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            filter: 'blur(36px) saturate(1.2)',
            transform: 'scale(1.2)',
            opacity: 0.55,
          }}
        />
      )}
      {/* Dark gradient overlays for header & action bar contrast. */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'linear-gradient(to bottom, rgba(12,16,24,0.85) 0%, rgba(12,16,24,0.45) 12%, rgba(12,16,24,0.55) 70%, rgba(12,16,24,0.92) 100%)',
        }}
      />

      <div
        ref={scrollEl}
        className="slide-scroll"
        style={{ position: 'relative', zIndex: 1 }}
      >
        {/* ── Header ───────────────────────────────────────────────────── */}
        <header
          className="flex items-center justify-between"
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 5,
            padding:
              'calc(env(safe-area-inset-top, 0px) + 12px) 16px 12px',
            background:
              'linear-gradient(to bottom, rgba(12,16,24,0.85), rgba(12,16,24,0))',
          }}
        >
          <span
            className="flex items-center gap-2"
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--text-primary)',
              maxWidth: '60%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={article.source.name}
          >
            {article.is_premium && (
              <Lock size={12} aria-label="Contenu premium" />
            )}
            {article.source.name}
          </span>
          <ScoreBadge score={article.relevance_score} scorer={article.scorer} />
        </header>

        {/* ── Hero image — kept inline below the header so the user always
            sees it even after scrolling a bit; the blurred background still
            colours the rest of the slide. */}
        {article.og_image_url && (
          <div
            style={{
              padding: '0 16px',
              marginTop: 4,
            }}
          >
            <img
              src={article.og_image_url}
              alt=""
              loading={imageEager ? 'eager' : 'lazy'}
              decoding="async"
              style={{
                width: '100%',
                maxHeight: 240,
                objectFit: 'cover',
                borderRadius: 18,
                boxShadow: '0 12px 32px rgba(0,0,0,0.45)',
              }}
            />
          </div>
        )}

        {/* ── Title + meta ──────────────────────────────────────────────── */}
        <div style={{ padding: '20px 20px 0' }}>
          <h1
            style={{
              fontSize: 24,
              fontWeight: 600,
              lineHeight: 1.25,
              color: 'var(--text-primary)',
              margin: '0 0 10px',
              wordBreak: 'break-word',
            }}
          >
            {article.title}
          </h1>
          <p
            style={{
              fontSize: 11,
              color: 'var(--text-tertiary)',
              margin: '0 0 14px',
            }}
          >
            {formatTimeAgo(article.published_at)}
          </p>

          {/* Keywords */}
          {article.keywords && article.keywords.length > 0 && (
            <div
              className="flex flex-wrap gap-1.5"
              style={{ marginBottom: 16 }}
            >
              {article.keywords.map((kw) => (
                <KeywordTag key={kw} term={kw} />
              ))}
            </div>
          )}

          {/* Executive summary — bullets when AI ran, otherwise hidden. */}
          {article.summary_executive && (
            <div
              style={{
                marginBottom: 16,
                padding: '14px 16px',
                borderRadius: 14,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <ExecutiveSummary text={article.summary_executive} />
            </div>
          )}

          {/* Short summary */}
          {article.summary_short && (
            <p
              style={{
                fontSize: 14,
                lineHeight: 1.55,
                color: 'var(--text-secondary)',
                margin: '0 0 16px',
              }}
            >
              {article.summary_short}
            </p>
          )}

          {/* Full crawled content — paragraphs, not raw HTML. The
              backend stores plain text from newspaper4k. */}
          {article.content && (
            <div
              style={{
                fontSize: 14,
                lineHeight: 1.65,
                color: 'var(--text-secondary)',
                marginBottom: 20,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {article.content}
            </div>
          )}

          {/* "Lire l'article complet" CTA */}
          <button
            type="button"
            onClick={handleOpenArticle}
            className="flex items-center justify-center gap-2"
            style={{
              width: '100%',
              padding: '12px 16px',
              borderRadius: 14,
              border: '1px solid var(--accent-border)',
              background: 'var(--accent-subtle)',
              color: 'var(--accent-text)',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {article.is_premium ? (
              <>
                <Lock size={14} />
                Voir sur le site (contenu limité)
              </>
            ) : (
              <>
                <ExternalLink size={14} />
                Lire l&apos;article complet
              </>
            )}
          </button>
        </div>

        {/* ── Scroll boundary hint ───────────────────────────────────────── */}
        <ScrollBoundaryHint bouncing={!nextVisible} />

        {/* Spacer so the action bar (≈ 84px) + BottomNav (≈ 76px) don't
            hide the hint at the bottom of the scrollable region. */}
        <div
          style={{
            height: 'calc(env(safe-area-inset-bottom, 0px) + 180px)',
          }}
        />


        {/* Invisible sentinel: the parent stitches the next slide's wrapper
            into this ref so the chevron stops bouncing on intersection. */}
        <div
          ref={(el) => {
            nextEl.current = el
            nextSentinelRef?.(el)
          }}
          aria-hidden
          style={{ height: 1 }}
        />
      </div>

      {/* ── Action bar (sticky) ─────────────────────────────────────────── */}
      <div
        className="flex items-center justify-center"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 'calc(env(safe-area-inset-bottom, 0px) + 76px)',
          zIndex: 6,
          gap: 48,
          padding: '14px 0',
          background:
            'linear-gradient(to top, rgba(12,16,24,0.92), rgba(12,16,24,0))',
        }}
      >
        <ActionButton
          icon={<ThumbsDown size={24} />}
          label="Dislike"
          active={disliked}
          activeColor="var(--action-dislike)"
          onClick={() => onReact(disliked ? 'none' : 'dislike')}
        />
        <ActionButton
          icon={<Bookmark size={24} />}
          label={state.is_saved ? 'Unsave' : 'Save'}
          active={state.is_saved}
          activeColor="var(--action-save)"
          onClick={onToggleSave}
        />
        <ActionButton
          icon={<ThumbsUp size={24} />}
          label="Like"
          active={liked}
          activeColor="var(--action-like)"
          onClick={() => onReact(liked ? 'none' : 'like')}
        />
      </div>
    </article>
  )
}

interface ActionButtonProps {
  icon: React.ReactNode
  label: string
  active: boolean
  activeColor: string
  onClick: () => void
}

const ActionButton = ({
  icon,
  label,
  active,
  activeColor,
  onClick,
}: ActionButtonProps) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    aria-pressed={active}
    style={{
      width: 56,
      height: 56,
      borderRadius: '50%',
      background: active
        ? 'rgba(12,16,24,0.55)'
        : 'rgba(12,16,24,0.40)',
      border: `1.5px solid ${active ? activeColor : 'rgba(255,255,255,0.18)'}`,
      color: active ? activeColor : 'var(--text-primary)',
      backdropFilter: 'blur(10px)',
      WebkitBackdropFilter: 'blur(10px)',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer',
      // SVG fill follows currentColor when the inner icon uses fill="currentColor".
      transition: 'color 0.15s ease, border-color 0.15s ease, background 0.15s ease',
    }}
  >
    {/* Filled vs outline rendered via SVG fill attribute on lucide icons. */}
    <span
      style={{
        display: 'inline-flex',
        fill: active ? 'currentColor' : 'none',
      }}
    >
      {icon}
    </span>
  </button>
)

/**
 * Renders an executive summary as a bullet list. The LLM is asked for one
 * bullet per line; we split on newlines and strip leading `-`, `*`, `•`.
 */
const ExecutiveSummary = ({ text }: { text: string }) => {
  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => l.replace(/^[-*•]\s*/, ''))
  return (
    <ul
      style={{
        margin: 0,
        paddingLeft: 18,
        fontSize: 13,
        lineHeight: 1.55,
        color: 'var(--text-secondary)',
      }}
    >
      {lines.map((line, i) => (
        <li key={i} style={{ marginBottom: 4 }}>
          {line}
        </li>
      ))}
    </ul>
  )
}
