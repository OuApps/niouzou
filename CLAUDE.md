# Niouzou — Agent Bootstrap

## What is this project?

Niouzou is a self-hostable, mobile-first news aggregator with a TikTok/Tinder-style swipe interface. Users swipe articles, the system learns their preferences via keyword weights, and surfaces only relevant content.

## Stack

| Layer | Tech |
|---|---|
| API | Python 3.13 / FastAPI / SQLAlchemy 2.0 async |
| PWA | React / TypeScript / Vite / Tailwind CSS |
| DB | PostgreSQL + pgvector (image `pgvector/pgvector:pg17`) |
| RSS | Miniflux (external Docker image, REST API only) |
| LLM | OpenRouter (optional) |
| Auth | JWT via python-jose + passlib |
| Scoring | `scoring_mode = classic` (default): TFIDFScorer or AIKeywordScorer (if OPENROUTER_API_KEY). `smart` (E16): Smart Match embedding k-NN |
| Embeddings | Qwen3-Embedding-0.6B local via sentence-transformers (optional extra `embeddings`) — E16 |

## Concepts to never confuse

- `keyword.salience` — how central a keyword is to an **article** (set once at enrichment)
- `keyword_weight` — how much a keyword influences a specific **user's** feed (learned from feedback)
- `article.relevance_score` — probability (0.0–1.0) the user will enjoy the article. Computed at enrichment; never recomputed in classic mode. In smart mode, articles from the last `SMART_RESCORE_WINDOW_DAYS` are re-scored nightly (E16-S3)
- `article.embedding` — 1024-dim semantic vector (title + summary), set at enrichment in both modes; NULL → Smart Match falls back to classic for that article

## Key rules

- Never put business logic in routers — routers call services
- Never call DB directly from a router
- `ScoringPipeline` is the only entry point for the classic scorers — never call them directly. Smart Match (`scoring/smart_match.py`, needs DB) is invoked only via `ScoringService.score_article_for_user`
- The embedding model is loaded only via `services/embedding_service.py` (lazy, worker process only). **Tests never load the real model** — inject fakes (`tests/fake_embeddings.py`; conftest has a tripwire)
- `BlobBackground` component must appear on every PWA screen
- All colors and styles from `docs/DESIGN_SYSTEM.md` — no improvising
- AI (OpenRouter) is optional — system must work fully without it (Smart Match too: embeddings are local)

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
  scoring/      ← BaseScorer, TFIDFScorer, AIKeywordScorer, ScoringPipeline, smart_match (E16)
  crons/        ← fetch, enrich, refresh_weights
  tools/        ← one-shot ops CLIs (backfill_embeddings)
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
Optional: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `SCORE_THRESHOLD`, `RANDOM_SURFACE_RATE`, `FEED_GRAVITY`, `SCORING_MODE`, `SMART_*` (E16 knobs)

The Miniflux API token is provisioned automatically from Miniflux's own DB
(`api/niouzou/services/miniflux_bootstrap.py`) — no env var.

## Local dev environment quirks

- **Use `docker-compose` (hyphen), not `docker compose`.** The maintainer's
  local Docker setup ships the standalone v1 binary; the Compose v2 plugin
  is not installed, so `docker compose -f …` fails with
  `unknown shorthand flag: 'f'`.
- **Container runtime is Colima**, sized lean (2 CPU / 2 GiB RAM / 10 GiB
  disk). Pulling large images may be tight — some multi-arch manifest images
  have triggered `exec format error` on this setup in the past
  (`postgres:17-alpine` was one such case). The current Postgres image,
  `pgvector/pgvector:pg17`, was validated on Colima on 2026-06-10.
  Running the full enrichment locally (embedding model, E16) needs more RAM:
  `colima start --memory 4`.
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