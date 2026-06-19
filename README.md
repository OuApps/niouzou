# Niouzou

**Your news feed, self-hosted and yours to tune.**

A swipe-based news reader that scores every article 0–100% on how likely *you*
are to care, and learns from each like/dislike. Two scoring engines run side by
side — LLM-extracted keyword weights and semantic k-NN over local embeddings —
and you pick which one drives the feed. No telemetry, no cloud lock-in, no black
box: inspect and edit every weight, and swap the LLM behind it for any OpenRouter
model.

[![CI](https://github.com/OuApps/niouzou/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/OuApps/niouzou/actions/workflows/ci.yml)
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/niouzou?referralCode=bGgJYu)
![Licence](https://img.shields.io/badge/licence-Apache%202.0%20%2B%20Commons%20Clause-blue)

![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)

| | | | |
|---|---|---|---|
| ![Feed](docs/assets/screen_1.png) | ![Explore & search](docs/assets/screen_2.png) | ![Saved](docs/assets/screen_3.png) | ![Keywords](docs/assets/screen_4.png) |

- **Self-hosted** — one-click Railway, or Docker Compose
- **Two scoring engines** — learned keyword weights ⊕ semantic k-NN over `pgvector`; pick which drives the feed
- **Local embeddings** — semantic vectors run on-device (Qwen3-Embedding-0.6B); the LLM that enriches articles is pluggable via any OpenRouter model
- **No black box** — every keyword weight is visible and editable; see why each article is promoted
- **Installable PWA** — swipe, save for later, full-text search, no app store

---

## How the scoring works

Two independent relevance scores per article, both computed at ingestion and
persisted side by side (`article_relevance_scores`):

1. **Keyword score** — an LLM (via OpenRouter) extracts weighted keywords from
   each article. Every like/dislike updates your personal keyword weights in
   real time (with decay), and new articles are scored against them before they
   reach your feed.
2. **Smart Match score** — a local embedding model turns each article's
   LLM-written summary into a 1024-dim vector in `pgvector`; the score is a k-NN
   vote over your liked and disliked history, no keywords involved.

Both scores depend on LLM enrichment (via OpenRouter) — keyword extraction for
the first, the article summary the embedding is built from for the second.

`SCORING_MODE` (`keyword` — the default — or `smart`) picks which score filters
and ranks the feed; flipping is instant, no re-scoring. `RANDOM_SURFACE_RATE`
injects a few low-score articles so you never fully seal the bubble.

Nothing is hidden: open the Keywords tab to read and edit every weight, or pin
keywords to bias either engine. Reset your profile any time from Settings.

<p align="center"><img src="docs/assets/screen_breakdown.png" width="300" alt="Score breakdown — keyword contributions and the closest Smart Match neighbours"></p>

---

## Under the hood

| Layer | What runs |
|---|---|
| **API** | Python 3.13 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic · JWT auth |
| **PWA** | React · TypeScript · Vite · Tailwind — installable, mobile-first |
| **Storage** | PostgreSQL 17 + `pgvector` (1024-dim article embeddings, k-NN) |
| **Ingestion** | Miniflux (RSS/Atom), bootstrapped over its REST API |
| **Embeddings** | Qwen3-Embedding-0.6B via `sentence-transformers`, in the worker, lazy-loaded |
| **LLM** | any OpenRouter model (`OPENROUTER_MODEL`) — summaries + keyword extraction |

---

## Self-hosting

### Local

```bash
git clone https://github.com/OuApps/niouzou.git && cd niouzou
cp .env.example .env && $EDITOR .env       # set JWT_SECRET, POSTGRES_PASSWORD + OPENROUTER_API_KEY
docker-compose up -d
```

Open **http://localhost:3000**, create your account, add an RSS feed, start
swiping. The **first account you create becomes the instance admin**; everyone
after is a regular user. Database migrations, the Miniflux admin user, and
Miniflux's API key are all provisioned automatically on the first boot — no UI
step.

---

## Deploy on Railway

Click the button above. It deploys the whole stack in one shot — **5 services**:
`api`, `pwa`, `miniflux`, `refresh-worker` and `Postgres`. Railway generates
`JWT_SECRET` for you at deploy time; set `OPENROUTER_API_KEY` to power the
recommendation features (summaries, keyword + semantic scoring). Niouzou
provisions its own Miniflux access token on first boot — no manual key step.

---

## Configuration

Almost every knob is an environment variable with a sane default. Seven of them
(✅ below) can also be changed live from the in-app **admin panel**; a few are
deploy-time only (Compose / build).

**Override order:** admin panel (stored in the DB) → environment variable →
built-in default. Editing one of the seven in the admin panel takes effect
immediately, no restart; clearing it there falls back to the env var.

| Setting | Env var | Default | Admin UI | What it does |
|---|---|---|---|---|
| Auth secret | `JWT_SECRET` | `change-me` | — | Signs auth tokens. **Set a long random string.** |
| Access token TTL | `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | — | Access-token lifetime (minutes). |
| Refresh token TTL | `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | — | Refresh-token lifetime (days). |
| OpenRouter key | `OPENROUTER_API_KEY` | — | ✅ | **Required for recommendations** — LLM summaries, keyword + semantic scoring. |
| OpenRouter model | `OPENROUTER_MODEL` | `google/gemma-4-26b-a4b-it:free` | ✅ | Any OpenRouter model id. |
| OpenRouter base URL | `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | — | API endpoint. |
| OpenRouter timeout | `OPENROUTER_TIMEOUT` | `60` | — | Per-request timeout (seconds). |
| Scoring mode | `SCORING_MODE` | `keyword` | ✅ | Active score: `keyword` or `smart`. |
| Score threshold | `SCORE_THRESHOLD` | `0.0` | ✅ | Min active score to surface (0–1). |
| Random surface rate | `RANDOM_SURFACE_RATE` | `0.05` | — | Share of random low-score articles (anti-bubble). |
| Feed gravity | `FEED_GRAVITY` | `1.5` | — | How fast older articles drop in ranking. |
| Cold-start threshold | `COLD_START_THRESHOLD` | `10` | — | Feedbacks below which the threshold is bypassed. |
| Max keywords / article | `MAX_KEYWORDS_PER_ARTICLE` | `6` | ✅ | Keyword cap stored per article. |
| Smart: neighbourhood | `SMART_TOPK` | `5` | — | k-NN neighbours per polarity. |
| Smart: dislike weight | `SMART_LAMBDA` | `0.8` | — | λ in `raw = S+ − λ·S−`. |
| Smart: sigmoid β | `SMART_BETA` | `2.0` | — | Steepness of the score sigmoid. |
| Smart: decay half-life | `SMART_DECAY_HALFLIFE_DAYS` | `90` | — | Feedback decay half-life (days). |
| Smart: rescore window | `SMART_RESCORE_WINDOW_DAYS` | `14` | — | Nightly rescore window (days). |
| Fetch interval | `CRON_FETCH_INTERVAL` | `15` | ✅ | RSS fetch + enrich cadence (minutes). |
| Enrich interval | `CRON_ENRICH_INTERVAL` | `30` | — | Enrichment pass cadence (minutes). |
| Nightly refresh hour | `CRON_NIGHTLY_REFRESH_HOUR` | `3` | ✅ | UTC hour of weight recompute + dual-score rescore. |
| Fetch batch size | `MINIFLUX_FETCH_BATCH_SIZE` | `100` | — | Entries pulled from Miniflux per run. |
| Enrich batch size | `ENRICH_BATCH_SIZE` | `50` | — | Articles enriched per run. |
| Embedding threads | `EMBEDDING_NUM_THREADS` | auto (≤4) | — | torch/OpenMP thread cap (worker only). |
| Premium cutoff | `PREMIUM_CONTENT_MAX_CHARS` | `800` | — | Below this length → flagged partial/paywall. |
| Boilerplate (exact) | `ENRICHMENT_BOILERPLATE_EXACT` | — | — | Extra paywall/CGU exact templates (`\|\|\|`-separated). |
| Boilerplate (markers) | `ENRICHMENT_BOILERPLATE_MARKERS` | — | — | Extra boilerplate marker groups. |
| Database DSN | `DATABASE_URL` | built from `POSTGRES_*` | — | Postgres connection (Compose-built). |
| Miniflux URL | `MINIFLUX_URL` | — | — | Miniflux instance URL. |
| App DB user / pass / name | `POSTGRES_USER` · `POSTGRES_PASSWORD` · `POSTGRES_DB` | `niouzou` | — | App database credentials (Compose). |
| Miniflux admin | `MINIFLUX_ADMIN_USERNAME` · `MINIFLUX_ADMIN_PASSWORD` | `admin` · `change-me` | — | RSS admin account, first boot (Compose). |
| Miniflux DB pass | `MINIFLUX_DB_PASSWORD` | `miniflux` | — | `miniflux` DB-user password (Compose). |
| PWA API URL | `VITE_API_URL` | `http://localhost:8000/api/v1` | — | Baked into the bundle at build time. |

**Admin panel only** (no env var): edit the LLM prompt bodies, compact/merge the
keyword vocabulary, pick the OpenRouter model from a live priced list, and manage
users (promote admin, reset password).

---

## Licence

Apache 2.0 + Commons Clause. Free to use, modify, and self-host for personal
or internal use. **Commercial hosting** as a service for third parties is not
permitted. See [`LICENSE`](LICENSE).
