// E24-S7 — Loupe: single-select tag filter, persisted per screen (Feed vs
// Explore/Search independently) in localStorage so it survives a reload.
// No server persistence — the Loupe is ephemeral UI state sent as `?tag=`.

import { useCallback, useState } from 'react'

import { tokens } from '../api'

type LoupeScreen = 'feed' | 'explore'

interface LoupeSnapshot {
  // Guard against another account's selection on a shared device — same
  // pattern as the Explore sessionStorage snapshot.
  owner: string | null
  tag: string | null
}

const storageKey = (screen: LoupeScreen) => `niouzou_loupe_${screen}`

function read(screen: LoupeScreen): string | null {
  try {
    const raw = localStorage.getItem(storageKey(screen))
    if (!raw) return null
    const snap = JSON.parse(raw) as LoupeSnapshot
    if (snap.owner !== tokens.email()) return null
    return snap.tag
  } catch {
    return null
  }
}

function write(screen: LoupeScreen, tag: string | null) {
  try {
    if (tag === null) {
      localStorage.removeItem(storageKey(screen))
    } else {
      const snap: LoupeSnapshot = { owner: tokens.email(), tag }
      localStorage.setItem(storageKey(screen), JSON.stringify(snap))
    }
  } catch {
    // Quota/private-mode failures just lose persistence, never the feature.
  }
}

/** Selected tag id for this screen's Loupe (null = no Loupe), with a setter
 *  that persists to localStorage. Call the setter with null on a backend 422
 *  (deleted tag) so the stale selection is silently cleaned up. */
export function useLoupe(
  screen: LoupeScreen,
): [string | null, (tag: string | null) => void] {
  const [tag, setTagState] = useState<string | null>(() => read(screen))
  const setTag = useCallback(
    (next: string | null) => {
      setTagState(next)
      write(screen, next)
    },
    [screen],
  )
  return [tag, setTag]
}
