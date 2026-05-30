# Architecture — Niouzou

## Service Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Railway / Docker Compose                   │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │ Miniflux │    │   FastAPI    │    │     React PWA        │   │
│  │  :8080   │◄───│   :8000      │◄───│  (nginx / :3000)     │   │
│  └──────────┘    └──────┬───────┘    └──────────────────────┘   │
│                         │  POST /admin/refresh                   │
│                  ┌──────▼────────────┐                          │
│                  │  Refresh Worker   │  ← always-on             │
│                  │  :8000 (internal) │                          │
│                  │  POST /run        │                          │
│                  │  ├─ cron_fetch    │  every 15 min            │
│                  │  ├─ cron_enrich   │  chained after fetch     │
│                  │  └─ refresh_wts   │  daily 03:00             │
│                  └──────┬────────────┘                          │
│                         │                                        │
│                  ┌──────▼───────┐                               │
│                  │  PostgreSQL  │                               │
│                  │   :5432      │                               │
│                  └──────────────┘                               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

External:
  OpenRouter API  (optional, LLM routing)
  Miniflux        (RSS collection, official Docker image)
```

> **Note — E8-S6 consolidation complete (2026-05-30)**: The three cron jobs
> (`cron_fetch`, `cron_enrich`, `cron_refresh_weights`) have been consolidated
> into the `refresh-worker` service using APScheduler. The old Railway cron
> services have been removed. The diagram above reflects the current (simplified)
> topology: 4 services total (`api`, `pwa`, `refresh-worker`, PostgreSQL).

---

## Terminology

| Term | Scope | Description |
|---|---|---|
| `keyword.salience` | article × keyword | How central a keyword is to the article (0.0→1.0). Set at enrichment time by LLM or TF-IDF. Never changes. |
| `keyword_weight` | user × keyword | How much a keyword positively or negatively influences this user's feed. Learned from feedback history. |
| `article.relevance_score` | user × article | Probability (0.0→1.0) that the user will enjoy the article. Computed at enrichment time, never recomputed. Surfaced in the feed UI. |

---

## Services

### Miniflux
- Official Docker image, never modified
- Manages RSS/Atom source subscriptions and raw feed polling
- Niouzou pulls from it via its REST API — treated as a read-only data source
- Has its own internal PostgreSQL (separate from Niouzou DB)

### FastAPI (back)
- Main API server
- Handles authentication, feed delivery, feedback reception
- On each like/dislike/save API call: upserts `article_feedbacks` (idempotent — repeated likes = 1 like) then synchronously recomputes `keyword_weights` for affected keywords (row-level lock)
- Also the base image for all cron jobs

### React PWA (front)
- Mobile-first swipe interface
- Built with Vite
- Installable as a PWA on Android / e/OS
- Communicates only with the FastAPI backend
- Displays `relevance_score` as a percentage on each article card

### PostgreSQL
- Single database for all Niouzou data
- Managed by Railway in production, Docker volume in self-hosted

### Cron Jobs
- Three cron jobs, all run from the same Docker image as FastAPI:
  - `python -m niouzou.crons.fetch`
  - `python -m niouzou.crons.enrich`
  - `python -m niouzou.crons.refresh_weights`

---

## Data Flow

### 1. Collection
```
Miniflux (polls RSS sources)
  → cron_fetch pulls new entries via Miniflux REST API
  → stores articles in Niouzou DB with status = "pending"
  → deduplication via miniflux_entry_id
```

### 2. Enrichment & scoring
```
cron_enrich picks articles with status = "pending"

  Content extraction:
  → newspaper4k fetches and extracts clean article content from URL
  → fallback to RSS content if fetch fails (paywall, block, etc.)

  Summarization:
  if OPENROUTER_API_KEY is set:
    → LLM generates summary_short
      (3 sentences, engaging tone, makes user want to click)
    → LLM generates summary_executive
      (bullet points, exhaustive, factual)
    → LLM extracts keywords with salience scores
      { "keywords": [{"term": "rust", "salience": 0.9}, ...] }
  else:
    → summary_short = newspaper4k built-in summary
    → summary_executive = null
    → TF-IDF keyword extraction with salience scores

  Scoring (per user):
  → relevance_score = normalize(
      Σ keyword.salience * keyword_weight(keyword, user)
    )
  → unknown keywords → keyword_weight = 0 (neutral, never penalizes)
  → relevance_score stored as float 0.0→1.0, never recomputed after this

  → article status set to "enriched"
  → article surfaced in feed if relevance_score > SCORE_THRESHOLD
    or randomly selected via RANDOM_SURFACE_RATE (anti-echo-chamber)
```

### 3. Feedback & synchronous weight update
```
User swipes in PWA
  → POST /feedback { article_id, action: like|dislike|skip|save }
  → upsert into article_feedbacks
    (idempotent: like×4 = like×1, last action wins)
  → save action also counts as +1 like for keyword_weight purposes
  → synchronous recompute of keyword_weights for affected keywords:
    keyword_weight(term, user) =
      Σ keyword.salience(term, article) * feedback_value(action)
      over all articles containing term
    where feedback_value: like|save = +1, dislike = -1, skip = 0
    (row-level lock on affected keyword_weights rows)
```

### 4. Daily weight refresh
```
cron_refresh_weights runs once per day
  → full recompute of all keyword_weights from all feedbacks
  → does NOT touch article.relevance_score (scores are frozen)
  → safety net for drift or inconsistency in keyword_weights only
```

---

## Scoring Pipeline

```python
class BaseScorer:
    def score(self, article: Article, user: User) -> float: ...
    # returns an unbounded float contribution

class TFIDFScorer(BaseScorer):
    # active only when OPENROUTER_API_KEY is not set
    # uses TF-IDF salience × user keyword_weights

class AIKeywordScorer(BaseScorer):
    # active only when OPENROUTER_API_KEY is set
    # uses LLM salience × user keyword_weights

# final score normalized to 0.0→1.0 (relevance_score)
raw = sum(scorer.score(article, user) for scorer in active_scorers)
article.relevance_score = normalize(raw)  # sigmoid or min-max over known range
```

**Key rules:**
- AI or TF-IDF, never both — no noise mixing
- Unknown keyword → weight = 0, never penalizes
- New users see everything (all weights = 0 → all scores neutral → all pass threshold)
- `relevance_score` is frozen at enrichment time, even as keyword_weights evolve

---

## Authentication

- JWT-based authentication via `python-jose` + `passlib`
- Email + password login
- All data scoped to `user_id` — multi-user by design
- User management UI out of scope for MVP

---

## Technology Choices

| Component | Technology | Rationale |
|---|---|---|
| API | Python / FastAPI | Async, typed, great for data pipelines |
| PWA | React + Vite | Fast dev, wide ecosystem, swipe libs available |
| Database | PostgreSQL | Single store, Railway native support |
| Auth | python-jose + passlib | Standard FastAPI JWT pattern, no third-party service |
| Content extraction | newspaper4k | Maintained, press-article oriented, clean API |
| LLM routing | OpenRouter | Pay-per-use, multi-provider, single API key |
| RSS collection | Miniflux | Battle-tested, clean REST API, official Docker image |

---

## Deployment

### Railway (SaaS)
- One Railway project, one service per component, each pointing at the repo
  with a per-service **Root Directory** (`/api`, `/pwa`) — the per-service
  `railway.toml` controls build/deploy.
- A single Postgres service hosts **two databases** on the same instance:
  the API's default DB and a sibling `miniflux` DB. The API's pre-deploy
  step (`python -m niouzou.scripts.ensure_miniflux_db && alembic upgrade head`)
  creates the `miniflux` database on first boot and runs migrations.
- The Miniflux service's `DATABASE_URL` references the same Postgres but the
  `miniflux` database (see README).
- The Miniflux API token is provisioned automatically: the API/crons share
  Postgres with Miniflux, so they resolve a token directly from Miniflux's
  `api_keys` table on first call (see `services/miniflux_bootstrap.py`).
  The token is generated and INSERTed idempotently; no env var, no UI step.
- Services communicate via Railway's internal network (`*.railway.internal`).
- **Cron consolidation (E8-S6, 2026-05-30)**:
  - Old separate Railway cron services (`cron-fetch`, `cron-enrich`, `cron-refresh-weights`) have been **removed**.
  - Cron jobs now consolidated into the `refresh-worker` service using APScheduler (Python).
  - `refresh-worker` runs:
    - `cron_fetch → cron_enrich` chain every `CRON_FETCH_INTERVAL` minutes (default 15)
    - `cron_refresh_weights` daily at hour `CRON_REFRESH_WEIGHTS_HOUR` UTC (default 03:00)
  - Mutual exclusion lock (`asyncio.Lock`) between scheduled runs and manual `POST /admin/refresh` prevents concurrent execution.
  - Configuration (fetch interval, weights refresh hour) is overridable via `PATCH /admin/config` (E8-S3) and persisted in `app_settings` table (E8-S2).
- **Service count**: Reduced from 6 to 4 services (`api`, `pwa`, `refresh-worker`, PostgreSQL).

### Docker Compose (self-hosted)
- `docker-compose.yml` at repo root — one-command stack
- A single Postgres instance hosts both the `niouzou` and `miniflux` databases
  (the `miniflux` user/db are created by `infra/postgres-init/`)
- One-shot `migrate` service runs Alembic before `api` accepts traffic
- The Miniflux API token is provisioned at runtime by the API/cron services
  themselves on first call — same mechanism as on Railway. No bootstrap
  container needed.
- Cron jobs wrap the one-shot scripts in a sleep loop (`restart: unless-stopped`)
- All configuration via `.env` (template: `.env.example`)
- `docker-compose.test.yml` is a separate file providing a tmpfs Postgres on
  port `5433` for the pytest suite, so the main stack stays lean and tests
  never touch real data

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string (built from `POSTGRES_*` inside compose) |
| `MINIFLUX_URL` | ✅ | Miniflux instance URL |
| `JWT_SECRET` | ✅ | Secret for JWT signing |
| `MINIFLUX_ADMIN_USERNAME` | ⚙️ compose | Admin user provisioned by Miniflux on first boot (default: `admin`) |
| `MINIFLUX_ADMIN_PASSWORD` | ⚙️ compose | Admin password (default: `adminpassword`) |
| `MINIFLUX_DB_PASSWORD` | ⚙️ compose | Password for the `miniflux` user inside the shared Postgres (default: `miniflux`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | ⚙️ compose | App database credentials (defaults: `niouzou`/`niouzou`/`niouzou`) |
| `OPENROUTER_API_KEY` | ❌ | Enables AI enrichment and scoring |
| `OPENROUTER_MODEL` | ❌ | Model to use (default: `nvidia/nemotron-3-super-120b-a12b:free`) |
| `SCORE_THRESHOLD` | ❌ | Minimum relevance_score to surface article (default: `0.0`) |
| `RANDOM_SURFACE_RATE` | ❌ | % of random articles in feed (default: `0.05`) |
| `FEED_GRAVITY` | ❌ | Controls how fast older articles drop in ranking (default: `1.5`) |
| `COLD_START_THRESHOLD` | ❌ | Number of feedbacks below which `SCORE_THRESHOLD` is bypassed — prevents an empty feed on day one (default: `10`) |
| `MAX_KEYWORDS_PER_ARTICLE` | ❌ | Cap on keywords stored per article — applied after extraction (default: `6`) |
| `CRON_FETCH_INTERVAL` | ❌ | Fetch + enrich chain interval in minutes (1–1440, default: `15`) — overridable via `PATCH /admin/config` (E8-S3) |
| `CRON_REFRESH_WEIGHTS_HOUR` | ❌ | Hour (0–23 UTC) when daily keyword-weight recompute runs (default: `3`) — overridable via `PATCH /admin/config` (E8-S3) |
| `VITE_API_URL` | ⚙️ pwa build | Baked into the bundle at build time; must be browser-reachable (default: `http://localhost:8000/api/v1`) |

---

## Key Design Decisions

**Miniflux as external dependency**
Miniflux is AGPL-licensed. Using it only via REST API keeps Niouzou under Apache 2.0 + Commons Clause without license contamination.

**Three distinct concepts, never conflated**
`keyword.salience` (article-level, set once) × `keyword_weight` (user-level, learned) = `relevance_score` (frozen at enrichment). Each has a single owner and a single moment of mutation.

**Scores frozen at enrichment**
`relevance_score` is computed once when an article is enriched, using keyword_weights as they are at that moment. It is never recomputed. This keeps the feed stable and the system simple.

**Synchronous weight update on feedback**
keyword_weights update immediately on like/dislike so the next enrichment run benefits from fresh weights. The daily `cron_refresh_weights` is a safety net only.

**Idempotent feedback**
`article_feedbacks` uses upsert — the last action wins. Tapping like four times has the same effect as tapping once.

**AI or TF-IDF, never both**
Mixing would introduce noise in keyword_weights and make scoring harder to reason about. TF-IDF is the clean fallback when no AI key is present.

**No message broker**
Status fields on articles (`pending` → `enriched`) replace a queue. Simple, observable, sufficient for the expected load.