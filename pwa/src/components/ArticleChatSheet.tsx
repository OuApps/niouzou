import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Send, Sparkles, X } from 'lucide-react'
import { ApiError, streamArticleChat } from '../api'
import type { ChatTurn } from '../api'
import type { FeedArticle } from '../types/api'

interface Props {
  article: Pick<FeedArticle, 'id' | 'title' | 'og_image_url' | 'source'>
  onClose: () => void
  /** E21-S8 — fired once, when the user sends their FIRST message (not on
   *  merely opening the sheet): starting a conversation is an engagement
   *  signal, the parent records the read-full-article bonus with it. */
  onFirstMessage?: () => void
}

// Starter suggestions shown while the thread is empty — three generic ways
// into any article, mirroring the mockup pills.
const SUGGESTIONS = [
  'Summarize this in one sentence',
  'Why does this matter?',
  'Give me more context',
]

// Swipe-down on the header region closes the sheet past this distance.
const SWIPE_CLOSE_PX = 60

// Abort the request if the first token hasn't arrived after this long —
// free-tier OpenRouter models can queue for minutes, and an infinite typing
// indicator with no way out is worse than an error + retry.
const FIRST_TOKEN_TIMEOUT_MS = 45_000

type Phase = 'idle' | 'waiting' | 'streaming'

/**
 * E21-S4 — Bottom sheet to chat with the LLM about an article (option A of
 * the E21 mockups). Deliberately a bottom sheet like the feed's score-debug
 * surface, NOT a `Modal`: it covers ~78% of the viewport, the article stays
 * visible (dimmed) behind, and a swipe-down / backdrop tap / Escape returns
 * to the feed.
 *
 * v1 is stateless (EPIC 21 decision #1): the thread lives in this component
 * and the full history is re-sent on every turn; closing the sheet drops the
 * conversation. Mounted lazily by the parent so nothing is fetched or built
 * before the first open.
 */
export const ArticleChatSheet = ({ article, onClose, onFirstMessage }: Props) => {
  const [thread, setThread] = useState<ChatTurn[]>([])
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [input, setInput] = useState('')

  const threadEl = useRef<HTMLDivElement | null>(null)
  const inputEl = useRef<HTMLInputElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  // The exact payload of the in-flight/last request, kept for retry.
  const lastSentRef = useRef<ChatTurn[] | null>(null)
  const touchStartY = useRef<number | null>(null)

  // Abort any in-flight stream when the sheet unmounts (close, slide change).
  useEffect(() => () => abortRef.current?.abort(), [])

  // Escape closes — same affordance as the app's modals.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // Keep the newest message/token in view. Imperative DOM scroll — the
  // recommended home for it is an effect keyed on the thread contents.
  useEffect(() => {
    const el = threadEl.current
    if (el) el.scrollTop = el.scrollHeight
  }, [thread, phase])

  const send = useCallback(
    (messages: ChatTurn[]) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      lastSentRef.current = messages

      setThread(messages)
      setPhase('waiting')
      setError(null)

      // Watchdog: a model that never produces a first token (queued free
      // tier, dead upstream) must not leave the typing indicator spinning
      // forever — abort and surface a retry instead.
      let stalled = false
      const watchdog = window.setTimeout(() => {
        stalled = true
        controller.abort()
      }, FIRST_TOKEN_TIMEOUT_MS)

      let acc = ''
      streamArticleChat(
        article.id,
        messages,
        {
          onToken: (delta) => {
            window.clearTimeout(watchdog)
            acc += delta
            setPhase('streaming')
            setThread([...messages, { role: 'assistant', content: acc }])
          },
          onError: (message) => {
            // Mid-stream failure: keep any partial text, surface a retry.
            setError(message)
          },
        },
        controller.signal,
      )
        .then(() => setPhase('idle'))
        .catch((e: unknown) => {
          window.clearTimeout(watchdog)
          if (e instanceof DOMException && e.name === 'AbortError') {
            if (!stalled) return // closed / superseded by a new send
            setPhase('idle')
            setError('The assistant is not responding. Try again.')
            return
          }
          setPhase('idle')
          setError(
            e instanceof ApiError ? e.message : 'The assistant is unavailable.',
          )
        })
    },
    [article.id],
  )

  const submit = (text: string) => {
    const question = text.trim()
    if (!question || phase !== 'idle') return
    // First message of the conversation → engagement signal (E21-S8).
    if (thread.length === 0) onFirstMessage?.()
    setInput('')
    // Strip a partial assistant tail left by an errored stream so the thread
    // we send always alternates cleanly and ends on this user turn.
    const base =
      thread.length > 0 && thread[thread.length - 1].role === 'assistant' && error
        ? thread.slice(0, -1)
        : thread
    send([...base, { role: 'user', content: question }])
  }

  const retry = () => {
    if (lastSentRef.current) send(lastSentRef.current)
  }

  // Swipe-down on the grabber/header closes the sheet (E21-S4).
  const onHeaderTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
  }
  const onHeaderTouchEnd = (e: React.TouchEvent) => {
    const start = touchStartY.current
    touchStartY.current = null
    if (start !== null && e.changedTouches[0].clientY - start > SWIPE_CLOSE_PX) {
      onClose()
    }
  }

  const busy = phase !== 'idle'

  // Portal to <body>: mounted inside the feed slide the sheet would live in
  // the `.feed-snap` z-10 stacking context, where the root-level BottomNav
  // (z-40) paints OVER it — hiding the composer behind the nav (E21 fix).
  return createPortal(
    <>
      {/* Backdrop — tap to dismiss, article stays visible behind. */}
      <div
        onClick={onClose}
        aria-hidden
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.55)',
          zIndex: 50,
        }}
      />
      <div
        role="dialog"
        aria-label={`Chat about: ${article.title}`}
        className="chat-sheet"
      >
        {/* Grabber + article context header — also the swipe-down handle. */}
        <div onTouchStart={onHeaderTouchStart} onTouchEnd={onHeaderTouchEnd}>
          <div
            aria-hidden
            style={{
              width: 38,
              height: 4,
              borderRadius: 2,
              background: 'rgba(255,255,255,0.2)',
              margin: '9px auto 5px',
            }}
          />
          <div
            className="flex items-center gap-2.5"
            style={{
              padding: '8px 14px 12px',
              borderBottom: '1px solid var(--divider)',
            }}
          >
            {article.og_image_url ? (
              <img
                src={article.og_image_url}
                alt=""
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  objectFit: 'cover',
                  flexShrink: 0,
                }}
              />
            ) : (
              <div
                aria-hidden
                className="flex items-center justify-center"
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: 'var(--accent-subtle)',
                  color: 'var(--accent)',
                  flexShrink: 0,
                }}
              >
                <Sparkles size={16} />
              </div>
            )}
            <div style={{ minWidth: 0, flex: 1 }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  lineHeight: 1.25,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {article.title}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                Grounded on this article · {article.source.name}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close chat"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                padding: 6,
                flexShrink: 0,
              }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Thread */}
        <div
          ref={threadEl}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {thread.length === 0 && (
            <div
              style={{
                fontSize: 12.5,
                lineHeight: 1.5,
                color: 'var(--text-secondary)',
                padding: '10px 13px',
                borderRadius: 16,
                borderBottomLeftRadius: 5,
                background: 'var(--glass-bg)',
                border: '1px solid var(--glass-border)',
                alignSelf: 'flex-start',
                maxWidth: '84%',
              }}
            >
              Ask anything about this article — details, context, or where the
              topic goes from here.
            </div>
          )}
          {thread.map((turn, i) => (
            <ChatBubble key={i} turn={turn} />
          ))}
          {phase === 'waiting' && <TypingIndicator />}
          {error && (
            <div
              className="flex items-center gap-2"
              style={{
                alignSelf: 'flex-start',
                fontSize: 12,
                color: 'var(--action-dislike)',
                padding: '8px 12px',
                borderRadius: 12,
                background: 'rgba(248,113,113,0.08)',
                border: '1px solid rgba(248,113,113,0.25)',
              }}
            >
              <span>{error}</span>
              <button
                type="button"
                onClick={retry}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-primary)',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  padding: 0,
                  textDecoration: 'underline',
                }}
              >
                Retry
              </button>
            </div>
          )}
        </div>

        {/* Starter suggestions — only before the first exchange. */}
        {thread.length === 0 && !busy && (
          <div
            className="flex flex-wrap gap-1.5"
            style={{ padding: '0 14px 10px' }}
          >
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => submit(s)}
                style={{
                  fontSize: 11,
                  padding: '6px 11px',
                  borderRadius: 16,
                  border: '1px solid rgba(255,255,255,0.10)',
                  background: 'rgba(255,255,255,0.05)',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Composer */}
        <div
          className="flex items-center gap-2"
          style={{
            padding: '11px 12px calc(11px + env(safe-area-inset-bottom, 0px))',
            borderTop: '1px solid var(--divider)',
          }}
        >
          <input
            ref={inputEl}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit(input)}
            placeholder="Ask a question…"
            aria-label="Ask a question about this article"
            style={{
              flex: 1,
              padding: '9px 14px',
              borderRadius: 20,
              border: '1px solid var(--glass-border)',
              background: 'rgba(255,255,255,0.06)',
              color: 'var(--text-primary)',
              // 16px, not the app's usual 13: iOS Safari zooms the page when
              // focusing any input below 16px, which wrecks a typing-heavy
              // surface like a chat composer.
              fontSize: 16,
              outline: 'none',
            }}
          />
          <button
            type="button"
            onClick={() => submit(input)}
            disabled={busy || input.trim() === ''}
            aria-label="Send"
            className="flex items-center justify-center"
            style={{
              width: 38,
              height: 38,
              borderRadius: '50%',
              border: 'none',
              background: 'var(--accent)',
              color: '#0c1018',
              cursor: 'pointer',
              flexShrink: 0,
              opacity: busy || input.trim() === '' ? 0.4 : 1,
              transition: 'opacity 0.15s ease',
            }}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </>,
    document.body,
  )
}

const ChatBubble = ({ turn }: { turn: ChatTurn }) => {
  const isUser = turn.role === 'user'
  return (
    <div
      style={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '84%',
        fontSize: 12.5,
        lineHeight: 1.5,
        padding: '10px 13px',
        borderRadius: 16,
        ...(isUser
          ? {
              background: 'var(--accent)',
              color: '#0c1018',
              fontWeight: 500,
              borderBottomRightRadius: 5,
            }
          : {
              background: 'var(--glass-bg)',
              border: '1px solid var(--glass-border)',
              color: 'rgba(255,255,255,0.88)',
              borderBottomLeftRadius: 5,
            }),
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {turn.content}
    </div>
  )
}

/** Three bobbing dots while the LLM hasn't produced its first token yet. */
const TypingIndicator = () => (
  <div
    aria-label="The assistant is thinking"
    className="flex items-center gap-1"
    style={{
      alignSelf: 'flex-start',
      padding: '13px 15px',
      borderRadius: 16,
      borderBottomLeftRadius: 5,
      background: 'var(--glass-bg)',
      border: '1px solid var(--glass-border)',
    }}
  >
    <span className="chat-typing-dot" />
    <span className="chat-typing-dot" />
    <span className="chat-typing-dot" />
  </div>
)
