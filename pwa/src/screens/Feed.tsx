import { useState, useCallback, useRef } from 'react'
import { useSprings, animated, to } from '@react-spring/web'
import { useDrag } from '@use-gesture/react'
import { ThumbsDown, Bookmark, ThumbsUp } from 'lucide-react'
import { BlobBackground } from '../components/BlobBackground'
import { BottomNav } from '../components/BottomNav'
import { ArticleCard } from '../components/ArticleCard'
import { MOCK_ARTICLES } from '../mocks/articles'
import { useFeedbackStore } from '../store/feedback'

const SWIPE_THRESHOLD = 100
const SWIPE_UP_THRESHOLD = 80
const PULL_THRESHOLD = 80

const from = (_i: number) => ({
  x: 0,
  y: 0,
  scale: 1,
  rot: 0,
  opacity: 1,
})

const to_idle = (gone: Set<number>) => (i: number) =>
  gone.has(i)
    ? { x: 0, y: -600, scale: 0.8, rot: 0, opacity: 0 }
    : { x: 0, y: 0, scale: 1, rot: 0, opacity: 1 }

export const Feed = () => {
  const [gone] = useState(() => new Set<number>())
  const [currentIndex, setCurrentIndex] = useState(0)
  const articles = MOCK_ARTICLES
  const setFeedback = useFeedbackStore((s) => s.setFeedback)

  // Pull-to-refresh state
  const [pullY, setPullY] = useState(0)
  const [pulling, setPulling] = useState(false)
  const touchStartY = useRef(0)
  const isPulling = useRef(false)

  const [springs, api] = useSprings(articles.length, (i) => ({
    ...to_idle(gone)(i),
    from: from(i),
  }))

  const resetFeed = useCallback(() => {
    gone.clear()
    setCurrentIndex(0)
    api.start(() => ({
      x: 0,
      y: 0,
      scale: 1,
      rot: 0,
      opacity: 1,
      immediate: true,
    }))
  }, [api, gone])

  const dismiss = useCallback(
    (index: number, dir: 'left' | 'right' | 'up') => {
      gone.add(index)

      const articleId = articles[index].id
      if (dir === 'right') setFeedback(articleId, 'like')
      else if (dir === 'left') setFeedback(articleId, 'dislike')
      else if (dir === 'up') setFeedback(articleId, 'save')

      api.start((i) => {
        if (i !== index) return
        const x = dir === 'left' ? -500 : dir === 'right' ? 500 : 0
        const y = dir === 'up' ? -600 : 0
        const rot = dir === 'left' ? -15 : dir === 'right' ? 15 : 0
        return {
          x,
          y,
          rot,
          scale: 0.8,
          opacity: 0,
          config: { friction: 30, tension: 200 },
        }
      })
      setCurrentIndex((prev) => Math.min(prev + 1, articles.length))
    },
    [api, articles, gone, setFeedback],
  )

  const bind = useDrag(
    ({ args: [index], active, movement: [mx, my], direction: [dx, dy], velocity: [vx, vy] }) => {
      const triggerRight = mx > SWIPE_THRESHOLD || (vx > 0.5 && dx > 0)
      const triggerLeft = mx < -SWIPE_THRESHOLD || (vx > 0.5 && dx < 0)
      const triggerUp = my < -SWIPE_UP_THRESHOLD || (vy > 0.5 && dy < 0)

      if (!active) {
        if (triggerRight) return dismiss(index, 'right')
        if (triggerLeft) return dismiss(index, 'left')
        if (triggerUp) return dismiss(index, 'up')

        api.start((i) => {
          if (i !== index) return
          return { x: 0, y: 0, rot: 0, scale: 1, opacity: 1 }
        })
        return
      }

      api.start((i) => {
        if (i !== index) return
        const rot = mx / 20
        return {
          x: mx,
          y: my,
          rot,
          scale: 1.02,
          opacity: 1,
          immediate: (key: string) => key === 'x' || key === 'y',
        }
      })
    },
    { filterTaps: true },
  )

  // Pull-to-refresh handlers
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
    isPulling.current = false
  }, [])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    const dy = e.touches[0].clientY - touchStartY.current
    if (dy > 0 && window.scrollY === 0) {
      isPulling.current = true
      setPulling(true)
      setPullY(Math.min(dy * 0.5, 120))
    }
  }, [])

  const handleTouchEnd = useCallback(() => {
    if (isPulling.current && pullY > PULL_THRESHOLD) {
      resetFeed()
    }
    setPullY(0)
    setPulling(false)
    isPulling.current = false
  }, [pullY, resetFeed])

  const pullProgress = Math.min(pullY / PULL_THRESHOLD, 1)

  return (
    <div
      className="flex flex-col min-h-dvh relative"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      <BlobBackground />

      {/* Pull-to-refresh indicator */}
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

      {/* Card stack */}
      <div
        className="relative z-10 flex-1 flex items-center justify-center"
        style={{ padding: '0 20px', minHeight: 460 }}
      >
        {currentIndex >= articles.length ? (
          <div className="text-center" style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
            <p style={{ fontSize: 32, marginBottom: 12 }}>You are all caught up</p>
            <p>Check back later for new articles</p>
          </div>
        ) : (
          springs.map((props, i) => {
            if (i < currentIndex || gone.has(i)) return null

            return (
              <animated.div
                key={articles[i].id}
                {...bind(i)}
                style={{
                  position: 'absolute',
                  width: '100%',
                  maxWidth: 360,
                  zIndex: articles.length - i,
                  transform: to(
                    [props.x, props.y, props.rot, props.scale],
                    (x, y, r, s) => `translate3d(${x}px,${y}px,0) rotate(${r}deg) scale(${s})`,
                  ),
                  opacity: props.opacity,
                  touchAction: 'none',
                }}
              >
                {/* Swipe tint overlays */}
                <animated.div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    borderRadius: 28,
                    zIndex: 10,
                    pointerEvents: 'none',
                    background: props.x.to((x) =>
                      x > 30
                        ? `rgba(72, 202, 228, ${Math.min(Math.abs(x) / 300, 0.25)})`
                        : x < -30
                          ? `rgba(248, 113, 113, ${Math.min(Math.abs(x) / 300, 0.25)})`
                          : 'transparent',
                    ),
                  }}
                />
                <ArticleCard article={articles[i]} />
              </animated.div>
            )
          })
        )}
      </div>

      {/* Action buttons */}
      {currentIndex < articles.length && (
        <div
          className="relative z-10 flex justify-center items-center gap-8"
          style={{ padding: '12px 0 24px' }}
        >
          <button
            onClick={() => dismiss(currentIndex, 'left')}
            aria-label="Dislike"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: 'var(--action-dislike)',
              fontSize: 26,
            }}
          >
            <ThumbsDown size={26} />
          </button>
          <button
            onClick={() => dismiss(currentIndex, 'up')}
            aria-label="Save"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: 'var(--action-save)',
              fontSize: 26,
            }}
          >
            <Bookmark size={26} />
          </button>
          <button
            onClick={() => dismiss(currentIndex, 'right')}
            aria-label="Like"
            style={{
              background: 'none',
              border: 'none',
              padding: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              color: 'var(--action-like)',
              fontSize: 26,
            }}
          >
            <ThumbsUp size={26} />
          </button>
        </div>
      )}

      <div style={{ height: 72 }} />
      <BottomNav />
    </div>
  )
}
