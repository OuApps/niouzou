# PRD — Niouzou

## Vision

Niouzou is a personal, self-hostable news aggregator with a mobile-first swipe interface inspired by TikTok/Tinder. Users swipe through articles, and the system learns their preferences to surface only relevant content.

Tagline: **"Take back control of your feed."**

---

## Problem

Existing aggregators (Feedly, Inoreader, Folo) are either:
- Not self-hostable
- Lacking preference learning
- Designed for desktop, not native mobile scrolling

No open source, self-hostable solution exists with a mobile-first UX and a personal recommendation engine.

---

## Target Users

### Persona 1 — The Self-Hoster (technical)
- Installs via Docker Compose on a NAS or VPS
- Wants full control over data, sources, and AI model
- Comfortable with an API key and a `.env` file
- Values: sovereignty, customization, zero cost

### Persona 2 — The General Public (SaaS)
- Uses the hosted Niouzou instance
- Doesn't know what RSS is
- Just wants an app that learns what they like to read
- Values: simplicity, zero configuration, smooth experience

---

## Features — MoSCoW

### Must Have (MVP)
- Add RSS/Atom sources
- Automatic article collection (via Miniflux)
- **Mobile swipe interface (like / dislike / skip)** — UI quality and modern design are a core product differentiator, not an afterthought
- Per-user article scoring and ranking based on learned preferences
- User feedback storage
- Simple authentication (email + password)
- **Multi-user by design** — all data scoped to a user from day one
- Modular scoring engine: TF-IDF baseline, AI-enhanced when `OPENROUTER_API_KEY` is set
- **AI article summaries** (via OpenRouter) — required for the full reading experience
- Railway one-click deployment
- Docker Compose for self-hosting

### Should Have (v1)
- LLM-extracted weighted keywords
- Cover image (og:image scraping, AI generation as fallback)
- Semantic scoring based on extracted keywords
- **Smart Match** (delivered, E16): embedding-based semantic scoring (local
  model, zero API cost) behind an admin toggle — Classic stays the default
- Newsletter support (dedicated email address per user)
- Personal reading statistics + ability to view and manually edit keyword scores

### Could Have (v2)
- Reddit as a source
- User management UI (admin panel, invitations)
- OPML export
- Native Android app
- User data monetization (e.g. anonymized analytics, opt-in)

### Won't Have (ever)
- Social features (sharing, comments, followers)
- Collaborative filtering (recommendations based on other users)
- Native iOS app
- Advertising
- Daily digest (email with top articles)

---

## Distribution Model

### Open Source (self-hosted)
- License: **GNU AGPL-3.0** (contributions under a CLA to keep a commercial/dual licence possible)
- Free to use, modify and self-host; network-service modifications must publish their source (AGPL §13)
- Prohibited: offering Niouzou as a paid hosted service for third parties
- Source code public on GitHub
- Not OSI-certified "open source" — this is **source available**

### SaaS (hosted Niouzou instance)
- Model: **Early Access** (waitlist, invitations)
- Paid after early access period
- Pricing TBD (likely freemium: limited free sources, unlimited paid)
- Hosted at `niouzou.tutus.ovh` during development

---

## Technical Constraints

- **Self-hosted infra**: Docker Compose, composable services
- **SaaS infra**: Railway (one service per component)
- **LLM**: OpenRouter as AI router (optional, enabled via `OPENROUTER_API_KEY`)
- **Without AI key**: system runs in degraded mode — no summaries, TF-IDF scoring only
- **Scoring engine**: modular — TF-IDF and AI layers cooperate when both are available, TF-IDF-only when AI is absent
- **Mobile first**: installable PWA, optimized for Android / e/OS
- **Miniflux**: used as an external dependency (official Docker image), never forked or modified

---

## Explicit Out of Scope

- No modification of Miniflux source code
- No iOS support in MVP
- No social features
- No Synology NAS hosting for SaaS (Railway only)
- No app store distribution (PWA only)