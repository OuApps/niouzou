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
> (`cron_fetch`, `cron_enrich`, `cron_nightly_refresh` — formerly
> `cron_refresh_weights`, renamed in E16-S9) have been consolidated into the
> `refresh-worker` service using APScheduler. The old Railway cron services
> have been removed. The diagram above reflects the current (simplified)
> topology: 4 services total (`api`, `pwa`, `refresh-worker`, PostgreSQL).

---

## Terminology

| Term | Scope | Description |
|---|---|---|
| `keyword.salience` | article × keyword | How central a keyword is to the article (0.0→1.0). Set at enrichment time by the LLM (extraction is LLM-only since E16-S8). Never changes. |
| `keyword_weight` | user × keyword | How much a keyword positively or negatively influences this user's feed. Learned from feedback history. |
| `keyword_score` | user × article | Probability (0.0→1.0) the user will enjoy the article, per the keyword method (AI keywords × user weights). NULL when the article has no keywords (LLM unavailable at enrichment). |
| `smart_score` | user × article | Same probability per the Smart Match method (embedding k-NN over the user's feedback history). NULL when the article has no embedding. Both scores are computed together at enrichment (E16-S8) and refreshed nightly within `SMART_RESCORE_WINDOW_DAYS` (E16-S9). |
| `article.embedding` | article | 1024-dim semantic vector of `title + summary_executive` (Qwen3-Embedding-0.6B, local, L2-normalised). Set at enrichment; NULL until computed. Powers `smart_score` (E16). |
| `scoring_mode` | instance | **Active-score selector** (E16-S9): `keyword` (the default) or `smart`. Does not gate computation — both scores always exist; it picks which column drives the feed threshold filter + ranking, so flipping it is instant. `classic` is accepted as a legacy alias of `keyword`. Admin toggle, `app_settings`-backed. |

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
- Displays both scores as two chips on each article card (keyword `#` +
  smart radar, E16-S10); the active one (per `scoring_mode`) is highlighted

### PostgreSQL
- Single database for all Niouzou data
- Managed by Railway in production, Docker volume in self-hosted

### Cron Jobs
- Three cron jobs, all run from the same Docker image as FastAPI:
  - `python -m niouzou.crons.fetch`
  - `python -m niouzou.crons.enrich`
  - `python -m niouzou.crons.nightly_refresh`
- E16 — the enrichment path also computes the article embedding. The model
  (~1.2 GB in fp16) loads lazily in the worker process on the first embed;
  budget ~1.5 GB extra RAM for the worker. The web API process never loads it.
  E17-S4 — the always-on worker now **unloads the model after each run**
  (`embedding_service.unload_embedding_model()` in `_guarded_run`'s `finally`)
  so idle RAM stays near zero; it reloads lazily on the next run (small
  cold-start). `CRON_FETCH_INTERVAL` defaults to 30 min in prod.
- One-shot ops CLIs:
  - `python -m niouzou.tools.backfill_embeddings` embeds legacy articles
    (batch 50, newest first, idempotent/resumable).
  - `python -m niouzou.tools.backfill_boilerplate_content` (`--all` for the
    whole corpus) re-enriches rows whose `content` is a paywall/CGU footer
    (E10-S6) — recovers the original RSS body from Miniflux, re-runs the
    normal enrichment, idempotent.

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
    OR returns recognised paywall/CGU boilerplate (E10-S6) — the RSS
    teaser then becomes content, which also trips is_premium correctly

  Summarization + keyword extraction (LLM-only since E16-S8):
  if OPENROUTER_API_KEY is set:
    → one combined LLM call generates summary_executive
      (4-6 markdown bullet points, ~15-25 words each — the only AI summary)
      AND extracts keywords with salience scores
      { "keywords": [{"term": "rust", "salience": 0.9}, ...] }
  else (or on LLM failure):
    → summary_executive = null (PWA renders the article body directly)
    → NO keywords stored → keyword_score = NULL for this article
      (the TF-IDF fallback was removed in E16-S8)

  summary_short is a legacy column retained for backward compat with
  already-enriched rows; new enrichments never populate it.

  Embedding (E16-S2, local, AI-independent — computed BEFORE scoring):
  → embedding = embed(title + " " + summary_executive)   [content[:1000] fallback]
  → local model (Qwen3-Embedding-0.6B via sentence-transformers), lazy-loaded
    in the worker process only — the web API never loads it
  → skipped with a warning if the optional `embeddings` extra isn't installed
    (smart_score then stays NULL for the article)

  Scoring (per user) — BOTH methods, whatever scoring_mode (E16-S8):
  → keyword_score = normalize(Σ keyword.salience × keyword_weight(kw, user))
    when the article has keywords, else NULL
    (unknown keywords → keyword_weight = 0: neutral, never penalizes)
  → smart_score = smart_score(article, user) — embedding k-NN over the
    user's feedbacked articles (see "Scoring Pipeline" below) — when the
    article has an embedding, else NULL
  → + one cold flag per method (keyword_cold_start / smart_cold_start)

  → article status set to "enriched" (even with both scores NULL)
  → article surfaced in feed if active_score >= SCORE_THRESHOLD
    (active = the scoring_mode column), or active score is cold/NULL,
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

### 4. Nightly refresh
```
cron_nightly_refresh runs once per day (renamed from cron_refresh_weights
in E16-S9 — it now refreshes both scores, not just the weights)
  → full recompute of all keyword_weights from all feedbacks
    (whatever the mode — keyword_weights drive keyword_score and the
     Keywords screen)
  → demote keyword_cold_start on rows whose keywords gained a user weight
  → rescore_recent: recomputes BOTH keyword_score and smart_score for
    articles ingested within SMART_RESCORE_WINDOW_DAYS, whatever
    scoring_mode — keeps the side-by-side comparison honest (a frozen
    keyword_score would diverge from the nightly-recomputed weights).
    Older rows stay frozen (gravity already pushed them out of the feed).
```

---

## Scoring Pipeline

```python
class BaseScorer:
    def score(self, keywords, user_weights) -> float: ...
    # pure maths: Σ salience × weight (shared by every scorer)

class AIKeywordScorer(BaseScorer):
    # LLM keyword *extraction* (used by the enrichment prompt path);
    # the scoring maths is the shared base implementation

class TFIDFScorer(BaseScorer):
    # kept for pipeline unit tests only — no longer wired into
    # cron_enrich since E16-S8 (keyword extraction is LLM-only)

# keyword_score, normalized to 0.0→1.0 — NULL when the article has no keywords
raw = scorer.score(article_keywords, user_weights)
keyword_score = normalize(raw)  # sigmoid; raw 0 → 0.5
```

### Smart Match (E16 — fills `smart_score`)

Unlike the scorers above (pure, no I/O), Smart Match needs the database (the
user's feedback neighbours), so it lives outside the `BaseScorer` hierarchy:
`ScoringService.score_article_for_user` calls `scoring/smart_match.py` on
every pass to fill the `smart_score` column, alongside the keyword score.

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
  semantics as the keyword method. `smart_cold_start` = user has no positive
  feedback.
- Article without embedding → `smart_score = NULL`; the ranked queries treat
  a NULL active score as cold (0.5 baseline, threshold bypass).
- No ANN index needed: the k-NN runs over the user's feedbacked articles
  (hundreds of rows), not the whole corpus.

**Key rules:**
- Keyword extraction is LLM-only (E16-S8). Without AI, `keyword_score` stays
  NULL — "works without AI" now means the smart pathway (embeddings are
  local); the keyword features (keyword score, pins, Keywords screen) are
  AI-only.
- Unknown keyword → weight = 0, never penalizes
- New users see everything (all weights = 0 → all scores neutral → all pass threshold)
- Both scores are persisted side by side; `scoring_mode` only selects which
  one filters + ranks the feed (flip = instant, no rescore). The nightly
  refresh recomputes both within the rescore window.
- The embedding is computed for every article (cheap, local) so the smart
  chip is populated whatever the active mode; switching modes is lossless
  in both directions (keyword_weights never stop updating).

---

## Authentication

- JWT-based authentication via `python-jose` + `passlib`
- Email + password login
- All data scoped to `user_id` — multi-user by design
- User management UI out of scope for MVP

### Known accepted advisories

Two transitive dependencies carry open CVEs with **no upstream fix released**.
Both are unreachable in Niouzou's configuration and are accepted (dismiss the
Dependabot alert as "not affected" — re-evaluate when a patched release ships):

- **`ecdsa` — CVE-2024-23342** (Minerva timing attack on ECDSA P-256). Pulled
  in by `python-jose`. We sign/verify JWTs with **HS256** (symmetric HMAC), so
  the `ecdsa` code path is never executed. python-jose hard-depends on the
  package, so it cannot be dropped without replacing the auth library; upstream
  considers the pure-Python timing leak unfixable.
- **`nltk` — CVE-2026-54293** (URL-encoded path traversal in
  `nltk.data.load()`). Pulled in by `newspaper4k`. We never pass untrusted
  paths to `nltk.data.load()`; latest release (3.9.4) is still unpatched.

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
    - `cron_nightly_refresh` daily at hour `CRON_NIGHTLY_REFRESH_HOUR` UTC (default 03:00) — renamed from `cron_refresh_weights` in E16-S9; the legacy `CRON_REFRESH_WEIGHTS_HOUR` env var is still read as a fallback
  - Mutual exclusion lock (`asyncio.Lock`) between scheduled runs and manual `POST /admin/refresh` prevents concurrent execution.
  - Configuration (fetch interval, nightly refresh hour) is overridable via `PATCH /admin/config` (E8-S3) and persisted in `app_settings` table (E8-S2).
- **Pipeline observability (E10-S1, 2026-06-01)**:
  - Every fetch+enrich cycle is recorded in `pipeline_runs`: when it ran, how long it took, how many articles it processed, whether it failed. `GET /stats` exposes the most recent row in its global `pipeline` block.
  - The refresh worker drives the per-article enrich loop directly (rather than calling `cron_enrich.run()`) so it can update the run row after each article and flip `articles.status` to a transient `'enriching'` for live progress visibility in `/stats`.
  - **Startup reaper**: before the scheduler starts, `UPDATE articles SET status='pending' WHERE status='enriching'` recovers any article left mid-flight by a previous worker crash.
  - **LLM retry**: the enrichment service retries a failing LLM call twice (backoff 1s, 3s) before giving up — transient OpenRouter blips don't leave articles without keywords (`keyword_score = NULL`) needlessly.
  - The old "Feed may be stalled" heuristic (based on the latest article's `created_at`) is gone; staleness is now driven by `pipeline_runs.completed_at` vs `cron_fetch_interval`, so a healthy cron tick producing nothing new no longer triggers a false alert.
- **OpenRouter cost tracking (E10-S7, 2026-06-14)**:
  - Every successful enrichment chat completion (`cron_enrich`/refresh worker, via `enrichment_resources`) appends a row to `llm_usage_log` with the $ cost and token counts.
  - The $ cost isn't on the chat-completion response in the installed OpenRouter SDK, so `OpenRouterClient` does a best-effort follow-up call to OpenRouter's `/generation` endpoint right after each completion; a lookup failure is logged at debug and never affects enrichment.
  - `GET /stats` sums `llm_usage_log.cost_usd` over 1h/6h/24h in its global `llm_cost` block — shown in the System panel as "Coût OpenRouter". Admin keyword-compaction LLM calls are out of scope (not routed through `enrichment_resources`).
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
| `SCORE_THRESHOLD` | ❌ | Minimum *active* score to surface an article (0.0–1.0, default: `0.0`; cold/NULL rows bypass it) — overridable via `PATCH /admin/config` (takes effect on the next `GET /feed` request) |
| `RANDOM_SURFACE_RATE` | ❌ | % of random articles in feed (default: `0.05`) |
| `FEED_GRAVITY` | ❌ | Controls how fast older articles drop in ranking (default: `1.5`) |
| `COLD_START_THRESHOLD` | ❌ | Number of feedbacks below which `SCORE_THRESHOLD` is bypassed — prevents an empty feed on day one (default: `10`) |
| `MAX_KEYWORDS_PER_ARTICLE` | ❌ | Cap on keywords stored per article — applied after extraction (default: `6`) |
| `CRON_FETCH_INTERVAL` | ❌ | Fetch + enrich chain interval in minutes (1–1440, default: `15`) — overridable via `PATCH /admin/config` (E8-S3) |
| `CRON_NIGHTLY_REFRESH_HOUR` | ❌ | Hour (0–23 UTC) of the nightly refresh: weights recompute + dual-score rescore (default: `3`) — overridable via `PATCH /admin/config`. The legacy name `CRON_REFRESH_WEIGHTS_HOUR` is still honoured as a fallback (E16-S9) |
| `SCORING_MODE` | ❌ | Active-score selector: `keyword` (default) or `smart` (E16-S9). Both scores are always computed; this picks which one filters + ranks the feed. `classic` accepted as legacy alias of `keyword`. Overridable via `PATCH /admin/config`; `smart` requires the `embeddings` extra + pgvector |
| `SMART_TOPK` | ❌ | Smart Match: k-NN neighbourhood size per polarity (default: `5`) |
| `SMART_LAMBDA` | ❌ | Smart Match: weight of the dislike term, `raw = S+ − λ·S−` (default: `0.8`) |
| `SMART_BETA` | ❌ | Smart Match: sigmoid steepness on the raw k-NN signal (default: `2.0`). Lower squashes scores onto ~0.5; raised from `0.5` so a threshold stays selective |
| `SMART_DECAY_HALFLIFE_DAYS` | ❌ | Smart Match: feedback decay half-life in days (default: `90`) |
| `SMART_RESCORE_WINDOW_DAYS` | ❌ | Smart Match: nightly rescoring window on `articles.created_at` (default: `14`) |
| `EMBEDDING_NUM_THREADS` | ❌ | Hard cap on the embedding model's torch/OpenMP thread pool (worker only). Unset → auto-detect the cgroup CPU quota, capped at 4. Containers expose the *host* core count to torch (e.g. 48) while the real quota is a few vCPU; oversubscription was measured at ~180× slowdown (142s → 0.8s/embed). Set low (e.g. `3`) to also trim vCPU-seconds billed |
| `ENRICHMENT_BOILERPLATE_EXACT` | ❌ | E10-S6 — extra paywall/CGU **exact templates** (full normalized-text match), `\|\|\|`-separated, merged with the built-in list. Add a verbatim footer here when one slips through (default: empty) |
| `ENRICHMENT_BOILERPLATE_MARKERS` | ❌ | E10-S6 — extra boilerplate **marker groups**: groups `\|\|\|`-separated, substrings within a group `&&`-separated; a group trips only when all its substrings co-occur. Use source-specific strings (emails, CMS phrasings), never generic RGPD/cookies vocabulary (default: empty) |
| `VITE_API_URL` | ⚙️ pwa build | Baked into the bundle at build time; must be browser-reachable (default: `http://localhost:8000/api/v1`) |

---

## Key Design Decisions

**Miniflux as external dependency**
Miniflux is AGPL-licensed. Using it only via REST API keeps Niouzou under Apache 2.0 + Commons Clause without license contamination.

**Three distinct concepts, never conflated**
`keyword.salience` (article-level, set once) × `keyword_weight` (user-level, learned) = `keyword_score`. Each has a single owner and a single moment of mutation. `smart_score` lives beside it, derived from `article.embedding` × feedback history (E16-S8).

**Dual scores, windowed rescore (E16-S8/S9)**
Both scores are computed once when an article is enriched, then refreshed nightly for the last `SMART_RESCORE_WINDOW_DAYS` only — the feed benefits retroactively from fresh feedback while older rows stay frozen (gravity already buried them; feed stability, system simplicity). `scoring_mode` selects the active column for filtering + ranking, so mode flips are instant and the two methods stay comparable in the UI.

**Local embeddings, optional dependency**
The embedding model (Qwen3-Embedding-0.6B, Apache 2.0) runs locally in the worker process — zero API cost, works without an OpenRouter key, multilingual. `sentence-transformers` is an optional extra (`embeddings`): without it `smart_score` stays NULL and the admin toggle refuses `smart` with an explicit 422. One vector per article, no chunking (the summary already condenses the topic; user multi-modality is handled by the k-NN, not by splitting articles). ⚠️ Changing the model means a full re-backfill — vectors from different models are not comparable.

**Synchronous weight update on feedback**
keyword_weights update immediately on like/dislike so the next enrichment run benefits from fresh weights. The daily `cron_nightly_refresh` is a safety net only.

**Idempotent feedback**
`article_feedbacks` uses upsert — the last action wins. Tapping like four times has the same effect as tapping once.

**Keyword extraction is LLM-only (E16-S8 — TF-IDF removed)**
The old TF-IDF fallback produced noisy keywords that polluted `keyword_weights`. Without AI, articles simply carry no keywords (`keyword_score = NULL`, rendered «–»); the smart pathway remains fully functional since embeddings are local. "Works without AI" therefore now means the smart pathway only.

**No message broker**
Status fields on articles (`pending` → `enriched`) replace a queue. Simple, observable, sufficient for the expected load.