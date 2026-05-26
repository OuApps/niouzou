# Architecture — Niouzou

## Service Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Railway / Docker Compose              │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ Miniflux │    │   FastAPI    │    │   React PWA      │  │
│  │  :8080   │◄───│   :8000      │◄───│   :3000          │  │
│  └──────────┘    └──────┬───────┘    └──────────────────┘  │
│                         │                                   │
│                  ┌──────▼───────┐                          │
│                  │  PostgreSQL  │                          │
│                  │   :5432      │                          │
│                  └──────────────┘                          │
│                                                             │
│  ┌─────────────────────────────────────────────────┐       │
│  │  Cron Jobs (same Docker image as FastAPI)        │       │
│  │  cron_fetch           — pull Miniflux → DB       │       │
│  │  cron_enrich          — extract + score articles │       │
│  │  cron_refresh_weights — daily keyword recompute  │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘

External:
  OpenRouter API  (optional, LLM routing)
  Miniflux        (RSS collection, official Docker image)
```

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
- One Railway project, one service per component
- Services communicate via Railway internal network
- Cron jobs configured in Railway dashboard
- Domain: `niouzou.tutus.ovh` (during development)

### Docker Compose (self-hosted)
- Single `docker-compose.yml` at repo root
- References official Miniflux and PostgreSQL images
- All configuration via `.env` file

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `MINIFLUX_URL` | ✅ | Miniflux instance URL |
| `MINIFLUX_API_KEY` | ✅ | Miniflux API key |
| `JWT_SECRET` | ✅ | Secret for JWT signing |
| `OPENROUTER_API_KEY` | ❌ | Enables AI enrichment and scoring |
| `OPENROUTER_MODEL` | ❌ | Model to use (default: `mistralai/mistral-small`) |
| `SCORE_THRESHOLD` | ❌ | Minimum relevance_score to surface article (default: `0.0`) |
| `RANDOM_SURFACE_RATE` | ❌ | % of random articles in feed (default: `0.05`) |
| `CRON_FETCH_INTERVAL` | ❌ | Fetch interval in minutes (default: `15`) |
| `CRON_ENRICH_INTERVAL` | ❌ | Enrichment interval in minutes (default: `30`) |

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