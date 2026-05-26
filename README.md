# Niouzou

**Take back control of your feed.**

Niouzou is a self-hostable news aggregator with a mobile-first swipe interface inspired by TikTok and Tinder. Swipe through articles, and the system quietly learns what you like — surfacing only what's relevant to you.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template)
![Licence](https://img.shields.io/badge/licence-Apache%202.0%20%2B%20Commons%20Clause-blue)

---

![Niouzou feed screenshot](docs/assets/screenshot.png)

---

## Why Niouzou?

Most news readers show you everything. Algorithms from big platforms show you what keeps you scrolling. Niouzou is different — it's yours, it runs on your infra, and it learns your actual preferences from your swipes.

- 🔒 **Your data, your server** — self-host on any machine that runs Docker
- 🧠 **Gets smarter over time** — keyword-based scoring learns from every like and dislike
- 📱 **Built for mobile** — installable PWA, swipe gestures, no app store needed
- ⚡ **AI optional** — works great without an API key, even better with one
- 🔓 **Source available** — read the code, modify it, run it yourself

---

## Features

- Swipe interface — like, dislike, skip, save for later
- Relevance score per article (0–100%) shown on every card
- Learns from your feedback — keyword weights updated in real time
- AI summaries via OpenRouter (short + executive format)
- RSS/Atom sources via Miniflux
- Watch Later list
- View and manually edit your keyword scores
- Multi-user ready by design
- Deploy in one click on Railway or self-host with Docker Compose

---

## Quickstart — Self-hosting

**Requirements**: Docker and Docker Compose installed.

```bash
# 1. Clone the repo
git clone https://github.com/yourname/niouzou.git
cd niouzou

# 2. Configure
cp .env.example .env
# Edit .env — set JWT_SECRET at minimum
# Add OPENROUTER_API_KEY to enable AI summaries (optional)

# 3. Start
docker compose up -d

# 4. Open
# PWA   → http://localhost:3000
# Admin → http://localhost:8080 (Miniflux)
```

That's it. Create an account, add your first RSS source, and start swiping.

---

## Deploy on Railway

Click the button above, set your environment variables, and you're live in under two minutes.

Required variables: `JWT_SECRET`
Optional: `OPENROUTER_API_KEY` for AI enrichment

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | ✅ | — | Secret for JWT signing — use a long random string |
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `MINIFLUX_URL` | ✅ | — | Miniflux instance URL |
| `MINIFLUX_API_KEY` | ✅ | — | Miniflux API key |
| `OPENROUTER_API_KEY` | ❌ | — | Enables AI summaries and keyword extraction |
| `OPENROUTER_MODEL` | ❌ | `mistralai/mistral-small` | Model to use via OpenRouter |
| `SCORE_THRESHOLD` | ❌ | `0.0` | Minimum relevance score to surface an article |
| `RANDOM_SURFACE_RATE` | ❌ | `0.05` | % of random articles shown (anti-echo-chamber) |
| `FEED_GRAVITY` | ❌ | `1.5` | Controls how fast older articles drop in ranking |

---

## How the scoring works

Every article gets a **relevance score** (0–100%) computed from your feedback history.

1. Each article is enriched with weighted keywords (LLM or TF-IDF)
2. Every like/dislike updates your personal keyword weights in real time
3. New articles are scored against your weights before appearing in your feed
4. A small % of low-score articles appear randomly to prevent filter bubbles

No black box. You can inspect and edit every keyword weight in the Keywords tab.

---

## Stack

| Layer | Tech |
|---|---|
| API | Python / FastAPI |
| PWA | React / TypeScript / Vite |
| Database | PostgreSQL |
| RSS | Miniflux |
| LLM (optional) | OpenRouter |
| Deployment | Railway / Docker Compose |

---

## Roadmap

See [`docs/EPICS.md`](docs/EPICS.md) for the full breakdown.

- [x] Architecture & design system
- [ ] EPIC 1 — PWA UI & navigation
- [ ] EPIC 2 — Foundations & ingestion
- [ ] EPIC 3 — API & basic scoring
- [ ] EPIC 4 — PWA API integration
- [ ] EPIC 5 — AI enrichment
- [ ] EPIC 6 — Packaging & open source

---

## Licence

Apache 2.0 + Commons Clause.

Free to use, modify, and self-host for personal or internal use.
**Commercial hosting** of Niouzou as a service for third parties is not permitted.

See [`LICENSE`](LICENSE) for details.