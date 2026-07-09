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
| Scoring | Dual persisted scores (E16-S8): `keyword_score` (AI keywords × user weights, LLM-only — no TF-IDF fallback anymore) ⊕ `smart_score` (Smart Match embedding k-NN). `scoring_mode` (`keyword` default \| `smart`) only selects which one drives the feed |
| Embeddings | Qwen3-Embedding-0.6B local via sentence-transformers (optional extra `embeddings`) — E16 |

## Concepts to never confuse

- `keyword.salience` — how central a keyword is to an **article** (set once at enrichment)
- `keyword_weight` — how much a keyword influences a specific **user's** feed (learned from feedback)
- `keyword_score` / `smart_score` — the TWO persisted probabilities (0.0–1.0) the user will enjoy the article, always computed together at enrichment whatever `scoring_mode` (E16-S8). NULL when the method has no input (no keywords / no embedding) → treated as cold by the feed (0.5 baseline, threshold bypass). Both refreshed nightly for articles in the last `SMART_RESCORE_WINDOW_DAYS` (E16-S9)
- `scoring_mode` — does NOT gate the computation; it only selects which score filters + ranks the feed (`keyword` | `smart`; flipping is instant, no rescore). `classic` is a legacy alias of `keyword`
- `article.embedding` — 1024-dim semantic vector (title + summary), set at enrichment whatever the mode; NULL → `smart_score` stays NULL for that article

## Key rules

- Never put business logic in routers — routers call services
- Never call DB directly from a router
- `ScoringPipeline` is the only entry point for the keyword scorers — never call them directly. Smart Match (`scoring/smart_match.py`, needs DB) is invoked only via `ScoringService.score_article_for_user`, which computes and upserts BOTH scores on every pass (E16-S8)
- Keyword extraction is **LLM-only** (E16-S8): no TF-IDF fallback in `cron_enrich`. `TFIDFScorer` survives for pipeline unit tests only
- The embedding model is loaded only via `services/embedding_service.py` (lazy, worker process only). **Tests never load the real model** — inject fakes (`tests/fake_embeddings.py`; conftest has a tripwire)
- `BlobBackground` component must appear on every PWA screen
- All colors and styles from `docs/DESIGN_SYSTEM.md` — no improvising
- AI (OpenRouter) is optional — but since E16-S8 "works without AI" means the **smart pathway only** (embeddings are local). Without AI: no keywords → `keyword_score = NULL`, pins/Keywords screen/keyword chip become AI-only; articles still surface

## Before writing any code

1. Read the relevant Epic + Story in `docs/EPICS.md`
2. Read `docs/ARCHITECTURE.md`
3. Read `docs/DATA_MODEL.md` (if touching DB)
4. Read `docs/API_SPEC.md` (if touching endpoints or API calls)
5. Read `docs/DESIGN_SYSTEM.md` (if touching frontend)
6. Read `docs/CONVENTIONS.md` for naming, structure, and patterns

## After finishing dev work

- If the work corresponds to a story in `docs/EPICS.md`, tick its checkbox (`[ ]` → `[x]`)
- Update any other `/docs` file impacted by the change (`ARCHITECTURE.md`, `DATA_MODEL.md`, `API_SPEC.md`, `CONVENTIONS.md`, `DESIGN_SYSTEM.md`) so they stay in sync with the code

## Repo structure

```
api/niouzou/
  routers/      ← thin, delegate to services
  services/     ← all business logic
  models/       ← SQLAlchemy ORM
  schemas/      ← Pydantic
  scoring/      ← BaseScorer, TFIDFScorer (tests only), AIKeywordScorer, ScoringPipeline, smart_match (E16)
  crons/        ← fetch, enrich, nightly_refresh (ex refresh_weights, E16-S9)
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
Optional: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `CHAT_MODEL` (article chat, falls back to `OPENROUTER_MODEL` — E21), `SCORE_THRESHOLD`, `RANDOM_SURFACE_RATE`, `FEED_GRAVITY`, `SCORING_MODE` (`keyword`|`smart`), `CRON_NIGHTLY_REFRESH_HOUR` (legacy `CRON_REFRESH_WEIGHTS_HOUR` still read as fallback), `SMART_*` (E16 knobs)

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

## Deployed environment (Railway)

When the maintainer asks about the "state of niouzou" or what's currently happening, this refers to the **deployed Railway environment**, not the local dev setup. The `railway` CLI (v5.12.1) is installed and authenticated — use it freely for read-only inspection, log review, and SQL debugging against the deployed DB.

- Project `niouzou` (workspace `fregogui's Projects`), single environment: `production`
- Services: `api`, `pwa`, `miniflux`, `refresh-worker`, plus a `Postgres` database (`ghcr.io/railwayapp-templates/postgres-ssl:18`)
- Public URLs: api → `https://api-production-1eb1.up.railway.app`, pwa → `https://pwa-production-98c2.up.railway.app`, miniflux → `https://miniflux-production-a749.up.railway.app`
- `railway status` — services, deployment status, DB volume usage
- `railway logs --service <api|pwa|miniflux|refresh-worker>` — build/deploy/HTTP logs
- `railway connect Postgres` — opens a `psql` shell on the production DB for ad-hoc SQL (e.g. inspecting `articles`, `keyword_weight`, scores)
- `railway run --service <name> -- <cmd>` — run a one-off command with that service's env vars

This is the **live production database** — `SELECT` queries are fine for debugging, but never run `UPDATE`/`DELETE`/DDL against it without explicit confirmation from the maintainer.

## Licence

GNU AGPL-3.0 — open source; a modified version run as a network service must publish its source (AGPL §13). Contributions under `CLA.md` (keeps a future commercial/dual licence possible).