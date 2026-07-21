import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ThumbsDown,
  ThumbsUp,
  Bookmark,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Lock,
  MessageCircle,
  Share2,
  Sparkles,
} from 'lucide-react'
import { ArticleChatSheet } from './ArticleChatSheet'
import { ScoreBadge } from './ScoreBadge'
import { ScoreDebugSheet } from './ScoreDebugSheet'
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
  /** E17-S2 — signals the user is leaving to read the article on its site, so
   *  the feed can keep its position instead of refetching when they return. */
  onOpenExternal?: () => void
  /** E23-S5 — share the Niouzou deep link. When set, a share button shows in
   *  the header. */
  onShare?: () => void
  /** E23-S4 — rendered outside the feed deck (deep-link `/article/:id`), so the
   *  "advance to next slide" affordances are dropped. */
  standalone?: boolean
  /** E23-S3 — the article isn't from one of the user's sources: no score, no
   *  feedback actions, no chat — just the reading view. */
  readOnly?: boolean
}

// Threshold below which we skip the "Lire plus" toggle entirely — short
// articles don't need the affordance and look weird with a button under them.
const CONTENT_PREVIEW_CHARS = 600

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
  onOpenExternal,
  onShare,
  standalone = false,
  readOnly = false,
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
  // Long-article collapse (UX pass): users who don't engage with a card need a
  // short scroll to the action bar, not a marathon. Anything past
  // CONTENT_PREVIEW_CHARS is hidden behind "Lire plus" until they ask.
  const [contentExpanded, setContentExpanded] = useState(false)
  // E21-S3/S4 — article chat sheet. Mounted lazily on first open; the
  // conversation state lives inside the sheet and dies with it (v1 is
  // ephemeral by design). Declared before the render-reset block below so
  // the reset can reference the setter.
  const [chatOpen, setChatOpen] = useState(false)
  // Collapse the "Lire plus" expansion when we switch to a different article.
  // Done during render (React's recommended pattern for resetting state on a
  // prop change) rather than synchronously in an Effect.
  const [renderedArticleId, setRenderedArticleId] = useState(article.id)
  if (article.id !== renderedArticleId) {
    setRenderedArticleId(article.id)
    setContentExpanded(false)
    setChatOpen(false)
  }
  // E10-S2 — open/closed state of the score-debug bottom sheet. The sheet
  // itself owns its fetch; we only pass the article id when open.
  const [debugOpen, setDebugOpen] = useState(false)
  // Swipe detection for vertical gestures at article boundaries (E11-S3).
  const touchStartRef = useRef<{
    y: number
    time: number
    atTop: boolean
    atBottom: boolean
  } | null>(null)

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

  // Swipe gesture detection at article boundaries (E11-S3): when at top/bottom
  // and the user swipes in the right direction, snap to next/previous article.
  const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    const touch = e.touches[0]
    const scroll = scrollEl.current
    if (!scroll) return
    const atTop = scroll.scrollTop <= 0
    const atBottom = Math.abs(scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight) <= 1
    touchStartRef.current = {
      y: touch.clientY,
      time: performance.now(),
      atTop,
      atBottom,
    }
  }

  const handleTouchEnd = (e: React.TouchEvent<HTMLDivElement>) => {
    const touch = e.changedTouches[0]
    const state = touchStartRef.current
    touchStartRef.current = null
    if (!state) return
    const dy = touch.clientY - state.y
    const dt = performance.now() - state.time
    // Only trigger snap if the gesture was fast or far enough.
    const SWIPE_DIST_THRESHOLD = 40
    const SWIPE_VELOCITY_THRESHOLD = 0.1 // px/ms
    const passesDistance = Math.abs(dy) > SWIPE_DIST_THRESHOLD
    const passesVelocity = Math.abs(dy) / Math.max(dt, 1) > SWIPE_VELOCITY_THRESHOLD
    if (!passesDistance && !passesVelocity) return
    // Snap only if the user swiped in a direction that makes sense at the boundary.
    if (dy > 0 && state.atTop) {
      // Swipe down at top → go to previous slide (if exists).
      const sibling = slideEl.current?.previousElementSibling
      if (sibling instanceof HTMLElement && sibling.classList.contains('feed-slide')) {
        sibling.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    } else if (dy < 0 && (state.atBottom || (state.atTop && state.atBottom))) {
      // Swipe up at bottom (or when article is short and at both) → next slide.
      const sibling = slideEl.current?.nextElementSibling
      if (sibling instanceof HTMLElement && sibling.classList.contains('feed-slide')) {
        sibling.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
  }

  const contentPreview = useMemo(() => {
    const text = article.content ?? ''
    if (text.length <= CONTENT_PREVIEW_CHARS) return { body: text, truncated: false }
    // Cut at the last whitespace before the budget so we don't slice mid-word.
    const slice = text.slice(0, CONTENT_PREVIEW_CHARS)
    const cut = slice.lastIndexOf(' ')
    return { body: (cut > 0 ? slice.slice(0, cut) : slice) + '…', truncated: true }
  }, [article.content])

  const handleOpenArticle = () => {
    onMarkRead()
    onOpenExternal?.()
    window.open(article.url, '_blank', 'noopener,noreferrer')
  }

  // Snap to the next slide in the feed-snap container. Triggered by tapping
  // the boundary hint at the bottom of the slide. ``scrollIntoView`` plays
  // well with ``scroll-snap-type`` on the parent (the snap engine picks up
  // the new position and aligns it). No-op on the last slide.
  const goToNext = () => {
    const sibling = slideEl.current?.nextElementSibling
    if (sibling instanceof HTMLElement && sibling.classList.contains('feed-slide')) {
      sibling.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
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
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
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
              <Lock size={12} aria-label="Premium content" />
            )}
            {article.source.name}
          </span>
          <div className="flex items-center gap-2">
            {onShare && (
              <button
                type="button"
                onClick={onShare}
                aria-label="Share this article"
                className="flex items-center justify-center"
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  border: '1px solid rgba(255,255,255,0.18)',
                  background: 'rgba(12,16,24,0.40)',
                  color: 'var(--text-primary)',
                  backdropFilter: 'blur(10px)',
                  WebkitBackdropFilter: 'blur(10px)',
                  cursor: 'pointer',
                }}
              >
                <Share2 size={16} />
              </button>
            )}
            {!readOnly && (
              <ScoreBadge
                keywordScore={article.keyword_score}
                keywordColdStart={article.keyword_cold_start}
                smartScore={article.smart_score}
                smartColdStart={article.smart_cold_start}
                activeMethod={article.active_method}
                onClick={() => setDebugOpen(true)}
              />
            )}
          </div>
        </header>

        {/* E23-S3 — deep-linked article from a source the user doesn't follow:
            surfaced read-only, no scoring. */}
        {readOnly && (
          <div
            style={{
              margin: '4px 16px 0',
              padding: '8px 12px',
              borderRadius: 12,
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.08)',
              color: 'var(--text-tertiary)',
              fontSize: 11,
              lineHeight: 1.4,
            }}
          >
            Cet article ne vient pas de vos sources — lecture seule, sans
            personnalisation.
          </div>
        )}

        {/* ── Hero image — kept inline below the header so the user always
            sees it even after scrolling a bit; the blurred background still
            colours the rest of the slide.

            When an article has no og:image we render a placeholder of the same
            footprint instead of collapsing the block: it keeps every slide
            visually uniform AND, on the Feed, guarantees the title clears the
            Loupe tag-filter chip row (an absolute overlay ~58px from the top),
            which would otherwise land on top of the title. */}
        <div
          style={{
            padding: '0 16px',
            marginTop: 4,
          }}
        >
          {article.og_image_url ? (
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
          ) : (
            <div
              aria-hidden
              className="flex items-center justify-center"
              style={{
                width: '100%',
                height: 160,
                borderRadius: 18,
                // Dark base so the white line-art mark pops, with a faint blob
                // tint on top for warmth (kept subtle over the dark base).
                background:
                  'linear-gradient(135deg, rgba(244,162,97,0.14), rgba(72,202,228,0.10)), #141a26',
                border: '1px solid rgba(255,255,255,0.06)',
                boxShadow: '0 12px 32px rgba(0,0,0,0.35)',
              }}
            >
              {/* Niouzou mark — white-bodied character with dark line detail,
                  the README-banner treatment. Rendered raw (no filter) so the
                  white body reads on the dark placeholder. */}
              <img
                src="/logo-mark.png"
                alt=""
                style={{
                  width: 124,
                  height: 124,
                }}
              />
            </div>
          )}
        </div>

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

          {/* Executive summary — bullets when AI ran, otherwise hidden. The
              top-left badge clearly labels the card as AI-generated. */}
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
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  marginBottom: 10,
                  color: 'var(--accent)',
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: 0.2,
                }}
                aria-label="AI-generated summary"
              >
                <Sparkles size={12} style={{ flexShrink: 0 }} />
                <span>AI Summary</span>
              </div>
              <ExecutiveSummary text={article.summary_executive} />
            </div>
          )}

          {/* Full crawled content — paragraphs, not raw HTML. The
              backend stores plain text from newspaper4k. Long bodies render
              collapsed so a disinterested user reaches the next-card affordance
              fast; a single tap expands them in place. */}
          {article.content && (
            <div style={{ marginBottom: 20 }}>
              <div
                style={{
                  fontSize: 14,
                  lineHeight: 1.65,
                  color: 'var(--text-secondary)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {contentExpanded || !contentPreview.truncated
                  ? article.content
                  : contentPreview.body}
              </div>
              {contentPreview.truncated && (
                <button
                  type="button"
                  onClick={() => setContentExpanded((v) => !v)}
                  className="flex items-center gap-1"
                  style={{
                    marginTop: 8,
                    padding: '6px 10px',
                    borderRadius: 999,
                    border: '1px solid rgba(255,255,255,0.10)',
                    background: 'rgba(255,255,255,0.04)',
                    color: 'var(--text-secondary)',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  aria-expanded={contentExpanded}
                >
                  {contentExpanded ? (
                    <>
                      <ChevronUp size={14} />
                      Show less
                    </>
                  ) : (
                    <>
                      <ChevronDown size={14} />
                      Read more
                    </>
                  )}
                </button>
              )}
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
                View on site (limited content)
              </>
            ) : (
              <>
                <ExternalLink size={14} />
                Read full article
              </>
            )}
          </button>

          {/* E21-S3 — chat entry point. AI-only: `summary_executive` doubles
              as the "this article was AI-enriched" signal (same gate as the
              summary card above), so instances without an OpenRouter key
              never show a button that would 409. Orange→cyan tint per the
              E21 mockups: related to the accent, distinct from the CTA. */}
          {!readOnly && article.summary_executive && (
            <button
              type="button"
              onClick={() => setChatOpen(true)}
              className="flex items-center justify-center gap-2"
              style={{
                width: '100%',
                marginTop: 10,
                padding: '12px 16px',
                borderRadius: 14,
                border: '1px solid var(--accent-border)',
                background:
                  'linear-gradient(120deg, rgba(244,162,97,0.20), rgba(72,202,228,0.14))',
                color: 'var(--text-primary)',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <MessageCircle size={14} />
              Chat about this article
              {/* Same AI marker as the summary card — this feature is
                  LLM-powered (E21-S8). */}
              <Sparkles size={12} style={{ color: 'var(--accent)' }} />
            </button>
          )}
        </div>

        {/* ── Scroll boundary hint ─────────────────────────────────────────
            Tappable: chevron + label together act as a single button that
            snaps to the next slide. We extend the button vertically with
            ``tailExtraPx`` so the *whole* region below the separator —
            including the area visually covered by the action bar's
            gradient — registers as a "next article" tap target. The
            action bar's container is pointer-events: none (auto on the
            buttons themselves), so taps on the gradient gap fall through
            to this hint underneath. */}
        {!standalone && (
          <ScrollBoundaryHint
            bouncing={!nextVisible}
            onActivate={goToNext}
            tailExtraPx={180}
          />
        )}


        {/* Invisible sentinel: the parent stitches the next slide's wrapper
            into this ref so the chevron stops bouncing on intersection. */}
        {!standalone && (
          <div
            ref={(el) => {
              nextEl.current = el
              nextSentinelRef?.(el)
            }}
            aria-hidden
            style={{ height: 1 }}
          />
        )}
      </div>

      {/* ── Action bar (sticky) ─────────────────────────────────────────────
          BottomNav is ``62px + safe-area`` tall (8 padding + 38 button +
          16 + safe-area). Setting ``bottom`` to that same value snaps the
          action bar gradient onto the top edge of the nav with no gap.
          The previous 76px left a ~14px light strip where the blurred
          background image showed through between the gradient and the nav
          surface (E10 follow-up). */}
      {!readOnly && (
      <div
        className="flex items-center justify-center"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 'calc(env(safe-area-inset-bottom, 0px) + 60px)',
          zIndex: 6,
          gap: 48,
          padding: '14px 0 18px',
          // The container ignores pointer events so a tap on the gradient
          // gap (between the like/dislike/save buttons) passes through to
          // the ScrollBoundaryHint underneath — the user can advance to
          // the next slide from anywhere in the bottom region, not just
          // on the small chevron+label area. Each ActionButton re-enables
          // pointer events on itself.
          pointerEvents: 'none',
          background:
            'linear-gradient(to top, rgba(12,16,24,0.95) 0%, rgba(12,16,24,0.85) 60%, rgba(12,16,24,0) 100%)',
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
      )}

      {/* Score-debug bottom sheet — only mounted while open so the fetch
          fires lazily on the user's first tap (E10-S2). */}
      <ScoreDebugSheet
        articleId={debugOpen ? article.id : null}
        onClose={() => setDebugOpen(false)}
      />

      {/* E21-S4 — article chat sheet, mounted lazily on open. Unmounting on
          close aborts the in-flight stream and drops the ephemeral thread.
          E21-S8 — sending the first message counts as engagement: same
          monotone read_full_article signal as "Read full article" (+0.5). */}
      {chatOpen && (
        <ArticleChatSheet
          article={article}
          onClose={() => setChatOpen(false)}
          onFirstMessage={onMarkRead}
        />
      )}
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
      // Parent action-bar is pointer-events: none so taps fall through to
      // the next-article hint. Each button reclaims its own hit area.
      pointerEvents: 'auto',
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
