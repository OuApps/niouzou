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

## Article Card (Feed)

Structure:
```
┌─────────────────────────────┐
│  [image / og:image]         │  185px tall
│  [source badge]  [score %]  │  absolute overlays
├─────────────────────────────┤
│  Title (15px/600)           │
│  Summary (12px, muted)      │
│  [keyword] [keyword] ...    │
│  ─────────────────          │
│  🕐 2h ago · 4 min read     │
└─────────────────────────────┘
```

- Source badge: bottom-left of image, dark glass pill
- Score badge: top-right of image, accent orange pill — shows `relevance_score` as `87%`
- Keywords: pill tags, `rgba(255,255,255,0.06)` bg
- Meta row: clock icon + time ago + read time, separated by `·`

---

## Action Buttons (Feed)

Three icon-only buttons, no border, no label:

```
👎 dislike    🔖 save    👍 like
```

```css
.action-btn {
  background: none;
  border: none;
  padding: 8px;
  border-radius: 50%;
  font-size: 26px;
}
.action-btn.dislike i { color: rgba(248, 113, 113, 0.70); }
.action-btn.save    i { color: rgba(249, 199, 79,  0.70); }
.action-btn.like    i { color: rgba(72,  202, 228, 0.85); }
```

---

## Bottom Navigation

4 icon-only items. Active state: accent orange + subtle bg.

```css
.bottom-nav {
  display: flex;
  justify-content: space-around;
  padding: 8px 20px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
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
| Feed | `ti-layout-cards` | `/` |
| Saved | `ti-bookmark` | `/saved` |
| Keywords | `ti-adjustments-horizontal` | `/keywords` |
| Profile | `ti-user` | `/profile` |

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
| Score | no icon — plain `%` text |
| Edit keyword | `Pencil` |
| Menu arrow | `ChevronRight` |
| Sign out | `LogOut` |

---

## Screen Inventory

| Screen | Route | Nav tab |
|---|---|---|
| Feed (swipe) | `/` | Feed |
| Article detail | `/articles/:id` | — |
| Saved | `/saved` | Saved |
| Keywords | `/keywords` | Keywords |
| Profile | `/profile` | Profile |
| Manage sources | `/sources` | — (from Profile) |
| Login | `/login` | — |
| Register | `/register` | — |

---

## Swipe Gestures (Feed)

| Gesture | Action |
|---|---|
| Swipe right | like |
| Swipe left | dislike |
| Swipe up | skip (next) |
| Tap card | open article detail |
| Tap ❤️ button | like |
| Tap 👎 button | dislike |
| Tap 🔖 button | save |

Recommended library: **`react-spring`** + **`@use-gesture/react`** for swipe detection and card animation.

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