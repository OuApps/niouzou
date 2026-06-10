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
| `article.relevance_score` | user × article | Probability (0.0→1.0) that the user will enjoy the article. Computed at enrichment time. In **classic** mode it is never recomputed; in **smart** mode (E16) articles ingested within the last `SMART_RESCORE_WINDOW_DAYS` are re-scored nightly. Surfaced in the feed UI. |
| `article.embedding` | article | 1024-dim semantic vector of `title + summary_executive` (Qwen3-Embedding-0.6B, local, L2-normalised). Set at enrichment regardless of mode; NULL until computed. Powers Smart Match (E16). |
| `scoring_mode` | instance | Active scoring engine: `classic` (keywords × weights, the default) or `smart` (embedding k-NN over the user's feedback history). Admin toggle, `app_settings`-backed. |

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
- E16 — the enrichment path also computes the article embedding. The model
  (~1.2 GB in fp16) loads lazily in the worker process on the first embed;
  budget ~1.5 GB extra RAM for the worker. The web API process never loads it.
- One-shot ops CLI: `python -m niouzou.tools.backfill_embeddings` embeds
  legacy articles (batch 50, newest first, idempotent/resumable).

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
    → LLM generates summary_executive
      (4-6 markdown bullet points, ~15-25 words each — the only AI summary)
    → LLM extracts keywords with salience scores
      { "keywords": [{"term": "rust", "salience": 0.9}, ...] }
  else:
    → summary_executive = null (PWA renders the article body directly)
    → TF-IDF keyword extraction with salience scores

  summary_short is a legacy column retained for backward compat with
  already-enriched rows; new enrichments never populate it.

  Scoring (per user):
  if scoring_mode = "classic" (default):
    → relevance_score = normalize(
        Σ keyword.salience * keyword_weight(keyword, user)
      )
    → unknown keywords → keyword_weight = 0 (neutral, never penalizes)
    → stored as float 0.0→1.0, never recomputed after this
  if scoring_mode = "smart" (E16):
    → relevance_score = smart_score(article, user)  — embedding k-NN over
      the user's feedbacked articles (see "Scoring Pipeline" below)
    → article without embedding → transparent fallback to the classic
      formula above (scorer column stamped accordingly)

  Embedding (E16-S2, always on, both modes):
  → embedding = embed(title + " " + summary_executive)   [content[:1000] fallback]
  → local model (Qwen3-Embedding-0.6B via sentence-transformers), lazy-loaded
    in the worker process only — the web API never loads it
  → skipped with a warning if the optional `embeddings` extra isn't installed

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
    (runs in both modes — keyword_weights stay alive under smart so the
     Keywords screen keeps working and the return to classic is lossless)
  → classic mode: does NOT touch article.relevance_score (scores are frozen)
  → smart mode (E16-S3): re-scores article_relevance_scores rows whose
    article was ingested within SMART_RESCORE_WINDOW_DAYS — the feed
    benefits retroactively from new feedback; older rows stay frozen
    (gravity already pushed them out of the feed)
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

### Smart Match (E16, `scoring_mode = 'smart'`)

Unlike the scorers above (pure, no I/O), Smart Match needs the database (the
user's feedback neighbours), so it lives outside the `BaseScorer` hierarchy:
`ScoringService.score_article_for_user` branches on `scoring_mode` and calls
`scoring/smart_match.py` directly.

```
S+ = Σ_{i ∈ topK(liked)}    sim(a, e_i) · value_i · decay(t_i)
S− = Σ_{j ∈ topK(disliked)} sim(a, e_j) · |value_j| · decay(t_j)

raw   = S+ − λ·S−
score = sigmoid(β·raw + Σ_{pinned kw ∩ keywords(a)} weight·salience)
```

- `sim` = pgvector cosine similarity; `value` = E9-S1 feedback signal
  ((±1 reaction) + 0.5·saved + 0.5·read); `decay(t) = 0.5^(age_days/halflife)`.
- **No user-profile centroid** — instance-based k-NN per polarity, so a user
  with several interest clusters (rugby + tech) is multi-modal by construction.
- Pinned keywords (`manually_overridden`) remain hard levers inside the
  sigmoid; learned weights become indicative only.
- `raw = 0` (no feedback / orthogonal candidate) → score 0.5: same neutral
  semantics as classic. `is_cold_start` (smart) = user has no positive feedback.
- Article without embedding → transparent fallback to the active classic
  scorer. The `article_relevance_scores.scorer` column traces provenance:
  `'tfidf' | 'ai_keyword' | 'smart_match'`.
- No ANN index needed: the k-NN runs over the user's feedbacked articles
  (hundreds of rows), not the whole corpus.

**Key rules:**
- AI or TF-IDF, never both — no noise mixing
- Unknown keyword → weight = 0, never penalizes
- New users see everything (all weights = 0 → all scores neutral → all pass threshold)
- `relevance_score` is frozen at enrichment time in classic mode; in smart
  mode only the nightly rescore window is recomputed
- The embedding is computed in both modes (cheap, local) so switching
  classic → smart is instant for recent articles; switching back is lossless
  (keyword_weights never stopped updating)

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
- **Pipeline observability (E10-S1, 2026-06-01)**:
  - Every fetch+enrich cycle is recorded in `pipeline_runs`: when it ran, how long it took, how many articles it processed, whether it failed. `GET /stats` exposes the most recent row in its global `pipeline` block.
  - The refresh worker drives the per-article enrich loop directly (rather than calling `cron_enrich.run()`) so it can update the run row after each article and flip `articles.status` to a transient `'enriching'` for live progress visibility in `/stats`.
  - **Startup reaper**: before the scheduler starts, `UPDATE articles SET status='pending' WHERE status='enriching'` recovers any article left mid-flight by a previous worker crash.
  - **LLM retry**: the enrichment service retries a failing LLM call twice (backoff 1s, 3s) before falling back to TF-IDF — transient OpenRouter blips no longer poison the AI/TF-IDF ratio.
  - The old "Feed may be stalled" heuristic (based on the latest article's `created_at`) is gone; staleness is now driven by `pipeline_runs.completed_at` vs `cron_fetch_interval`, so a healthy cron tick producing nothing new no longer triggers a false alert.
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
| `SCORE_THRESHOLD` | ❌ | Minimum relevance_score to surface article (0.0–1.0, default: `0.0`) — overridable via `PATCH /admin/config` (takes effect on the next `GET /feed` request) |
| `RANDOM_SURFACE_RATE` | ❌ | % of random articles in feed (default: `0.05`) |
| `FEED_GRAVITY` | ❌ | Controls how fast older articles drop in ranking (default: `1.5`) |
| `COLD_START_THRESHOLD` | ❌ | Number of feedbacks below which `SCORE_THRESHOLD` is bypassed — prevents an empty feed on day one (default: `10`) |
| `MAX_KEYWORDS_PER_ARTICLE` | ❌ | Cap on keywords stored per article — applied after extraction (default: `6`) |
| `CRON_FETCH_INTERVAL` | ❌ | Fetch + enrich chain interval in minutes (1–1440, default: `15`) — overridable via `PATCH /admin/config` (E8-S3) |
| `CRON_REFRESH_WEIGHTS_HOUR` | ❌ | Hour (0–23 UTC) when daily keyword-weight recompute runs (default: `3`) — overridable via `PATCH /admin/config` (E8-S3) |
| `SCORING_MODE` | ❌ | Scoring engine: `classic` (default) or `smart` (E16). Overridable via `PATCH /admin/config`; `smart` requires the `embeddings` extra + pgvector |
| `SMART_TOPK` | ❌ | Smart Match: k-NN neighbourhood size per polarity (default: `5`) |
| `SMART_LAMBDA` | ❌ | Smart Match: weight of the dislike term, `raw = S+ − λ·S−` (default: `0.8`) |
| `SMART_BETA` | ❌ | Smart Match: sigmoid steepness on the raw k-NN signal (default: `0.5`) |
| `SMART_DECAY_HALFLIFE_DAYS` | ❌ | Smart Match: feedback decay half-life in days (default: `90`) |
| `SMART_RESCORE_WINDOW_DAYS` | ❌ | Smart Match: nightly rescoring window on `articles.created_at` (default: `14`) |
| `VITE_API_URL` | ⚙️ pwa build | Baked into the bundle at build time; must be browser-reachable (default: `http://localhost:8000/api/v1`) |

---

## Key Design Decisions

**Miniflux as external dependency**
Miniflux is AGPL-licensed. Using it only via REST API keeps Niouzou under Apache 2.0 + Commons Clause without license contamination.

**Three distinct concepts, never conflated**
`keyword.salience` (article-level, set once) × `keyword_weight` (user-level, learned) = `relevance_score` (frozen at enrichment). Each has a single owner and a single moment of mutation.

**Scores frozen at enrichment (classic) / windowed rescore (smart)**
In classic mode, `relevance_score` is computed once when an article is enriched, using keyword_weights as they are at that moment, and never recomputed — feed stability, system simplicity. Smart Match (E16) deliberately relaxes this for *recent* articles only: the nightly rescore recomputes the last `SMART_RESCORE_WINDOW_DAYS` of scores so the feed benefits retroactively from fresh feedback, while older rows stay frozen (gravity already buried them).

**Local embeddings, optional dependency**
The embedding model (Qwen3-Embedding-0.6B, Apache 2.0) runs locally in the worker process — zero API cost, works without an OpenRouter key, multilingual. `sentence-transformers` is an optional extra (`embeddings`): without it the instance runs classic only and the admin toggle refuses `smart` with an explicit 422. One vector per article, no chunking (the summary already condenses the topic; user multi-modality is handled by the k-NN, not by splitting articles). ⚠️ Changing the model means a full re-backfill — vectors from different models are not comparable.

**Synchronous weight update on feedback**
keyword_weights update immediately on like/dislike so the next enrichment run benefits from fresh weights. The daily `cron_refresh_weights` is a safety net only.

**Idempotent feedback**
`article_feedbacks` uses upsert — the last action wins. Tapping like four times has the same effect as tapping once.

**AI or TF-IDF, never both**
Mixing would introduce noise in keyword_weights and make scoring harder to reason about. TF-IDF is the clean fallback when no AI key is present.

**No message broker**
Status fields on articles (`pending` → `enriched`) replace a queue. Simple, observable, sufficient for the expected load.