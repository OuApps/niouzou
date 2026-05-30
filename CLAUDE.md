# Niouzou — Agent Bootstrap

## What is this project?

Niouzou is a self-hostable, mobile-first news aggregator with a TikTok/Tinder-style swipe interface. Users swipe articles, the system learns their preferences via keyword weights, and surfaces only relevant content.

## Stack

| Layer | Tech |
|---|---|
| API | Python 3.13 / FastAPI / SQLAlchemy 2.0 async |
| PWA | React / TypeScript / Vite / Tailwind CSS |
| DB | PostgreSQL |
| RSS | Miniflux (external Docker image, REST API only) |
| LLM | OpenRouter (optional) |
| Auth | JWT via python-jose + passlib |
| Scoring | TFIDFScorer (default) or AIKeywordScorer (if OPENROUTER_API_KEY set) |

## Three concepts to never confuse

- `keyword.salience` — how central a keyword is to an **article** (set once at enrichment)
- `keyword_weight` — how much a keyword influences a specific **user's** feed (learned from feedback)
- `article.relevance_score` — probability (0.0–1.0) the user will enjoy the article (computed once at enrichment, never recomputed)

## Key rules

- Never put business logic in routers — routers call services
- Never call DB directly from a router
- `ScoringPipeline` is the only entry point for scoring — never call scorers directly
- `BlobBackground` component must appear on every PWA screen
- All colors and styles from `docs/DESIGN_SYSTEM.md` — no improvising
- AI (OpenRouter) is optional — system must work fully without it

## Before writing any code

1. Read the relevant Epic + Story in `docs/EPICS.md`
2. Read `docs/ARCHITECTURE.md`
3. Read `docs/DATA_MODEL.md` (if touching DB)
4. Read `docs/API_SPEC.md` (if touching endpoints or API calls)
5. Read `docs/DESIGN_SYSTEM.md` (if touching frontend)
6. Read `docs/CONVENTIONS.md` for naming, structure, and patterns

## Repo structure

```
api/niouzou/
  routers/      ← thin, delegate to services
  services/     ← all business logic
  models/       ← SQLAlchemy ORM
  schemas/      ← Pydantic
  scoring/      ← BaseScorer, TFIDFScorer, AIKeywordScorer, ScoringPipeline
  crons/        ← fetch, enrich, refresh_weights
  migrations/   ← Alembic

pwa/src/
  api/          ← typed API client
  components/   ← reusable UI (BlobBackground, ArticleCard, BottomNav...)
  screens/      ← one file per route
  hooks/
  store/        ← Zustand (auth)
  types/        ← mirrors API schemas
```

## Environment variables

See `docs/ARCHITECTURE.md` for the full list.
Required: `DATABASE_URL`, `MINIFLUX_URL`, `JWT_SECRET`
Optional: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `SCORE_THRESHOLD`, `RANDOM_SURFACE_RATE`, `FEED_GRAVITY`

The Miniflux API token is provisioned automatically from Miniflux's own DB
(`api/niouzou/services/miniflux_bootstrap.py`) — no env var.

## Local dev environment quirks

- **Use `docker-compose` (hyphen), not `docker compose`.** The maintainer's
  local Docker setup ships the standalone v1 binary; the Compose v2 plugin
  is not installed, so `docker compose -f …` fails with
  `unknown shorthand flag: 'f'`.
- **Container runtime is Colima**, sized lean (2 CPU / 2 GiB RAM / 10 GiB
  disk). Pulling large images may be tight — prefer `postgres:17` over
  multi-arch manifest images that have triggered `exec format error` on
  this setup in the past (`postgres:17-alpine` was one such case).
- **Tests need the Postgres test container running** before pytest can do
  anything: `docker-compose -f docker-compose.test.yml up -d` (port 5433),
  then `DATABASE_URL=postgresql://niouzou:niouzou@localhost:5433/niouzou_test
  uv run --project api pytest`. Tests skip cleanly if Postgres is
  unreachable.
- **No real Miniflux DB in tests.** `tests/conftest.py` short-circuits
  `miniflux_bootstrap._cached_key` so `SourcesService` / `cron_fetch` never
  try to open the sibling `miniflux` database. Miniflux HTTP is mocked with
  respx — leave that pattern alone.

## Licence

Apache 2.0 + Commons Clause — self-hosting allowed, commercial hosting of this software for third parties is not.