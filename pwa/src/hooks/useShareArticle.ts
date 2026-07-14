import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * E23-S5 — share a Niouzou article by its deep link.
 *
 * Prefers the native share sheet (`navigator.share`, mobile PWAs) and falls
 * back to copying the link to the clipboard with a transient toast. The URL is
 * built from the current origin, so a shared `/article/{id}` link opens the
 * same instance the sharer is on.
 */
export function useShareArticle() {
  const [toast, setToast] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  const flash = useCallback((message: string) => {
    setToast(message)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setToast(null), 2000)
  }, [])

  const share = useCallback(
    async (id: string, title: string) => {
      const url = `${window.location.origin}/article/${id}`
      try {
        if (navigator.share) {
          await navigator.share({ title, url })
          return
        }
        await navigator.clipboard.writeText(url)
        flash('Lien copié')
      } catch (e) {
        // The user dismissing the native share sheet isn't an error.
        if (e instanceof DOMException && e.name === 'AbortError') return
        // navigator.share failed (or no clipboard) — try a plain copy.
        try {
          await navigator.clipboard.writeText(url)
          flash('Lien copié')
        } catch {
          flash('Partage indisponible')
        }
      }
    },
    [flash],
  )

  return { share, toast }
}
