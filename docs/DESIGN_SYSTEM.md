# Design System — Niouzou

## Philosophy

- **Dark, immersive**: deep dark background with animated pastel blobs
- **Glassmorphism**: cards float over the background with blur + semi-transparent fill
- **Rounded**: generous border-radius everywhere, pill shapes for badges and tags
- **Minimal chrome**: no unnecessary borders, labels, or decorations
- **Mobile-first**: all sizing and spacing optimized for 375px viewport

---

## Color Tokens

### Background
```css
--bg-base: #0c1018;          /* app background */
```

### Blobs (animated, fixed behind everything)
```css
--blob-orange: #f4a261;
--blob-cyan:   #48cae4;
--blob-yellow: #f9c74f;
```

### Accent (primary brand color)
```css
--accent:         #f4a261;   /* orange — active states, logo highlight */
--accent-subtle:  rgba(244, 162, 97, 0.10);
--accent-border:  rgba(244, 162, 97, 0.40);
--accent-text:    #fcd9b6;
```

### Actions
```css
--action-like:    rgba(72, 202, 228, 0.85);   /* cyan */
--action-dislike: rgba(248, 113, 113, 0.70);  /* red  */
--action-save:    rgba(249, 199, 79, 0.70);   /* yellow */
```

### Glass surfaces
```css
--glass-bg:     rgba(255, 255, 255, 0.07);
--glass-border: rgba(255, 255, 255, 0.11);
--glass-blur:   24px;
```

### Text
```css
--text-primary:   #ffffff;
--text-secondary: rgba(255, 255, 255, 0.50);
--text-tertiary:  rgba(255, 255, 255, 0.30);
--text-disabled:  rgba(255, 255, 255, 0.20);
```

### Dividers
```css
--divider: rgba(255, 255, 255, 0.06);
```

---

## Typography

- **Font**: `Inter`, fallback `system-ui, sans-serif`
- **Weights used**: 400 (body), 600 (titles, values)

| Role | Size | Weight |
|---|---|---|
| App logo | 19px | 600 |
| Card title | 15px | 600 |
| Body / summary | 12px | 400 |
| Badge / tag / meta | 10–11px | 400–600 |
| Section label | 11px | 600 — uppercase, letter-spacing 0.8px |
| Stat value | 18px | 600 |

---

## Border Radius

| Element | Radius |
|---|---|
| Phone frame / large cards | 28px |
| Menu rows, stat cards, keyword rows | 16px |
| Menu icons | 10px |
| Badges, pills, tags, nav active state | 20px (pill) |
| Avatar | 50% |

---

## Animated Background Blobs

Three blobs, `position: fixed`, behind all content. Each animates independently.

```css
.bg-blobs {
  position: fixed;
  inset: 0;
  overflow: hidden;
  z-index: 0;
  pointer-events: none;
}

.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(65px);
  opacity: 0.45;
  animation: blobMove 22s ease-in-out infinite alternate;
}

/* Blob positions */
.blob-1 {
  width: 260px; height: 260px;
  background: #f4a261;          /* orange */
  top: -80px; left: -60px;
  animation-duration: 24s;
}
.blob-2 {
  width: 220px; height: 220px;
  background: #48cae4;          /* cyan */
  bottom: -40px; right: -50px;
  animation-duration: 19s;
  animation-delay: -7s;
}
.blob-3 {
  width: 180px; height: 180px;
  background: #f9c74f;          /* yellow */
  top: 45%; left: 20%;
  animation-duration: 28s;
  animation-delay: -13s;
}

@keyframes blobMove {
  0%   { transform: translate(0, 0) scale(1); }
  33%  { transform: translate(25px, -18px) scale(1.07); }
  66%  { transform: translate(-18px, 28px) scale(0.94); }
  100% { transform: translate(12px, 8px) scale(1.03); }
}
```

---

## Glass Card

Base card used across all screens.

```css
.card {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.11);
  border-radius: 28px;                        /* large cards */
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
}

/* Compact variant (menu rows, keyword rows, stat cards) */
.card-sm {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 16px;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}
```

---

## Feed Slide (fullscreen — E9-S2)

The feed is a vertical scroll-snap container; each article fills the screen.

```
┌────────────────────────────────┐  ← 100dvh (never 100vh — see below)
│  [og:image blurred bg]         │
│  source badge      [score %]   │  sticky top
├────────────────────────────────┤
│  [og:image hero, rounded]      │
│  Title (24px / 600)            │
│  [keyword] [keyword] ...       │
│  ┌── exec summary bullets ──┐  │  (AI-only)
│  Summary (14px, muted)         │
│  Crawled content (when present)│
│  [Lire l'article complet ↗]    │
│  ── scroll boundary ──         │
│  ▼ Niouzou logo ▼              │
│  ── ─────────── ──             │
├────────────────────────────────┤
│  👎       🔖       👍          │  sticky bottom, above BottomNav
└────────────────────────────────┘
```

### Viewport — `100dvh`, never `100vh`

Safari iOS and Chrome Android shrink the visible viewport whenever the URL
bar is in view. `100vh` reports the *expanded* viewport, which overflows the
scroll-snap container and clips the bottom action bar / hides the chevron.
Use `100dvh` for any screen that owns the full viewport (Feed slides, login,
empty state shells). Fallback chain: `100dvh` → `100svh` → `100vh`.

### Scroll boundary hint (`ScrollBoundaryHint`)

End-of-slide pedagogical marker so users learn to re-scroll for the next
article:
- 1px horizontal divider (60% width, centred)
- Niouzou logomark (32px, `opacity: 0.6`)
- `ChevronDown` (20px, `var(--text-tertiary)`) — animated:
  ```css
  @keyframes bounce-soft {
    0%, 100% { transform: translateY(0); }
    50%      { transform: translateY(4px); }
  }
  ```
- Label *"Article suivant"* (12px, `var(--text-tertiary)`, opacity 0.5)

The bounce stops automatically when the next slide enters the viewport: the
parent slide flips `data-bouncing="false"` via `IntersectionObserver`, and
the chevron animation detaches.

### Feed action bar (sticky bottom)

Three circular glass buttons, 56×56, sitting above the BottomNav.

| Button | Outline color | Active fill |
|---|---|---|
| Dislike (`ThumbsDown`) | `rgba(255,255,255,0.18)` border | `var(--action-dislike)` |
| Save (`Bookmark`) | same | `var(--action-save)` |
| Like (`ThumbsUp`) | same | `var(--action-like)` |

Re-tap on the active reaction returns it to `none`. Save and like are
mutually independent. Like and dislike are mutually exclusive.

---

## Bottom Navigation (E9-S4)

4 icon-only items. Active state: accent orange + subtle bg.

```css
.bottom-nav {
  display: flex;
  justify-content: space-around;
  padding: 8px 20px calc(env(safe-area-inset-bottom, 0px) + 16px);
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(12, 16, 24, 0.85);
  backdrop-filter: blur(20px);
}
.nav-item {
  padding: 8px 14px;
  border-radius: 20px;
  color: rgba(255, 255, 255, 0.30);
  font-size: 22px;
}
.nav-item.active {
  color: #f4a261;
  background: rgba(244, 162, 97, 0.10);
}
```

| Tab | Icon | Route |
|---|---|---|
| Feed | `LayoutGrid` | `/` |
| Explore | `Compass` | `/explore` |
| Saved | `Bookmark` | `/saved` |
| Profile | `User` | `/profile` |

Keywords is no longer a top-level tab — it lives in the Profile menu now
(between "Manage sources" and the Admin/System group).

---

## Explore (E9-S3)

The Explore screen ships with two tabs — **Lus** (History — already-impressed
articles) and **Nouveaux** (New — enriched, unseen). Both use the same row
layout, identical to Saved (`pwa/src/screens/Saved.tsx`):

```
┌──────────────────────────────────────────────────────┐
│  [thumb 64x64]   source · score%                     │
│                  Title (line-clamp 2)                │
│                  🔖 👍 👎 📖   (History only)        │
│                  il y a 2h                           │
└──────────────────────────────────────────────────────┘
```

- The state-icons row (`Bookmark` / `ThumbsUp` / `ThumbsDown` / `BookOpen`)
  is **only rendered in History** — by definition the New tab has no state
  to show. Active = fully coloured + `fill: currentColor`; inactive =
  `var(--text-tertiary)` outline with reduced opacity.
- Tap row → `navigate('/?start=' + article.id)`. The Feed reads `?start=` on
  mount, asks the backend for a pivoted first page, and clears the URL param
  so subsequent refreshes don't re-apply the pivot.
- Tab switcher is a pill group (`gap: 4`, `border-radius: 24`) anchored
  below the header. Active state mirrors the BottomNav: accent text on
  `var(--accent-subtle)` background.
- Infinite scroll follows the Saved.tsx pattern (`IntersectionObserver`
  sentinel + per-tab cursor state).

### Filter bar (E11-S2)

Two horizontally scrollable chip rows sit between the tab switcher and the
article list:

```
Score :    [Tous✓] [≥ 25 %] [≥ 50 %] [≥ seuil (60 %)] [≥ 75 %]
Sources :  [Toutes✓] [Le Monde] [HN] [Pragmatic Engineer] …
```

- Each row is `display: flex; gap: 6; overflow-x: auto; scrollbar-width: none`
  prefixed by a tiny uppercase label (`fontSize: 10`, `text-tertiary`).
- Score row: single-select; **"Tous"** sends no `min_score`, the percentage
  chips send `0.25 / 0.5 / 0.75`, and **"≥ seuil"** sends
  `stats.score_threshold`. The threshold chip is hidden when
  `score_threshold` is `0.0` or has not yet loaded.
- Sources row: multi-select. **"Toutes"** clears the selection; tapping any
  other chip toggles that source in/out and implicitly deselects "Toutes".
  Names longer than 18 chars are truncated with an ellipsis. The whole row
  is hidden when the user has 0 or 1 source.
- Filters are **per-tab** — switching Nouveaux ↔ Lus keeps each side's
  selection.
- Pull-to-refresh (`BlobBackground.onRefresh`) resets both tabs to the
  default (`Tous` / `Toutes`) before refetching.
- Empty state with at least one non-default filter shows
  *"Aucun résultat avec ces filtres."* + a `Réinitialiser les filtres`
  button instead of the standard Compass empty state.

### `FilterChip`

`pwa/src/components/FilterChip.tsx` — the chip primitive used by the filter
bar above. Active state: `border: 1px solid var(--accent)`, background
`var(--accent-subtle)`, text `var(--accent)`. Inactive: borderless
(`1px solid rgba(255,255,255,0.08)`), text `var(--text-secondary)`,
background `rgba(255,255,255,0.05)`. Sized at `padding: 5px 12px`,
`fontSize: 11`, `borderRadius: 16`.

---

## Icons

Library: **Lucide React** (`lucide-react`) for React components.

| Context | Icon |
|---|---|
| Like | `ThumbsUp` |
| Dislike | `ThumbsDown` |
| Save / Saved | `Bookmark` |
| Feed | `LayoutGrid` |
| Keywords | `SlidersHorizontal` |
| Profile | `User` |
| RSS source | `Rss` |
| Clock / time | `Clock` |
| Score (TF-IDF) | `Hash` |
| Score (AI keyword) | `Sparkles` |
| Score (Smart Match) | `Radar` |
| Edit keyword | `Pencil` |
| Menu arrow | `ChevronRight` |
| Sign out | `LogOut` |

---

## Screen Inventory

| Screen | Route | Nav tab |
|---|---|---|
| Feed (fullscreen slides) | `/` | Feed |
| Explore | `/explore` | Explore |
| Saved | `/saved` | Saved |
| Profile | `/profile` | Profile |
| Keywords | `/keywords` | — (from Profile) |
| Manage sources | `/sources` | — (from Profile) |
| Admin | `/admin` | — (admins only, from Profile) |
| Login | `/login` | — |
| Register | `/register` | — |

The standalone Article detail view (`/articles/:id`) was removed in **E9-S2**
— the fullscreen slide carries the same information inline. Any stale link
redirects to `/`.

### Profile menu items (top to bottom)

1. Manage sources
2. Keywords (E9-S4)
3. Administration (if `is_admin`)
4. Sign out
5. System (collapsible health panel)

---

## Feed Interaction Model (E9-S2)

| Gesture | Action |
|---|---|
| Vertical scroll inside slide content | scroll the article (content scrolls until end) |
| Continue scrolling past the end | snap to the next slide |
| Tap `ThumbsUp` | toggle reaction `like ⇄ none` |
| Tap `ThumbsDown` | toggle reaction `dislike ⇄ none` |
| Tap `Bookmark` | toggle `is_saved` |
| Tap "Lire l'article complet" | marks `read_full_article=true` + opens external URL in a new tab |

All feedback dispatches are **optimistic** — the icon flips instantly,
`POST /feedback` is fire-and-forget in the background. On failure the
overlay is rolled back so the user can re-tap. Like and dislike are
mutually exclusive; save and reaction are independent.

The scroll-snap pattern relies on:
- container `scroll-snap-type: y mandatory`
- slide `scroll-snap-align: start; scroll-snap-stop: always; height: 100dvh; overflow-y: auto`
- inner scrollable `overscroll-behavior-y: contain` so swipe inertia at the
  end of the content propagates to the parent (next slide), not the body.

---

## PWA Configuration

```json
{
  "name": "Niouzou",
  "short_name": "Niouzou",
  "theme_color": "#0c1018",
  "background_color": "#0c1018",
  "display": "standalone",
  "orientation": "portrait"
}
```