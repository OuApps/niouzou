# Niouzou

**Your news feed, self-hosted and yours to tune.**

A swipe-based news reader that scores every article 0–100% on how likely *you*
are to care, and learns from each like/dislike. Two scoring engines run side by
side — LLM-extracted keyword weights and semantic k-NN over local embeddings —
and you pick which one drives the feed. No telemetry, no cloud lock-in, no black
box: inspect and edit every weight, swap the LLM, or run with no AI key at all.

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

- 🔒 **100% self-hosted** — Docker or one-click Railway; your data never leaves your box, zero telemetry
- 🧠 **Two scoring engines** — learned keyword weights ⊕ semantic k-NN over `pgvector`; pick which drives the feed, flip instantly
- 🤖 **Local-first AI** — embeddings run on-device (Qwen3-Embedding-0.6B); LLM enrichment is optional and pluggable via any OpenRouter model
- 🔍 **No black box** — every keyword weight is visible and editable; a tunable random-surface rate keeps you out of the filter bubble
- 📱 **Installable PWA** — swipe, save for later, full-text search, no app store

---

## Under the hood

| Layer | What runs |
|---|---|
| **API** | Python 3.13 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic · JWT auth |
| **PWA** | React · TypeScript · Vite · Tailwind — installable, mobile-first |
| **Storage** | PostgreSQL 17 + `pgvector` (1024-dim article embeddings, k-NN) |
| **Ingestion** | Miniflux (RSS/Atom), bootstrapped over its REST API |
| **Embeddings** | Qwen3-Embedding-0.6B via `sentence-transformers`, in the worker, lazy-loaded |
| **LLM** | any OpenRouter model (`OPENROUTER_MODEL`) — summaries + keyword extraction, fully optional |

Routers stay thin and delegate to services; scoring goes through a single
pipeline; the embedding model never loads in the API process. The deep dives
live in [`docs/`](docs/) (`ARCHITECTURE`, `DATA_MODEL`, `API_SPEC`,
`CONVENTIONS`).

---

## Self-hosting

You need Docker. That's it.

```bash
git clone https://github.com/OuApps/niouzou.git && cd niouzou
cp .env.example .env && $EDITOR .env       # set JWT_SECRET + POSTGRES_PASSWORD
docker-compose up -d
```

Open **http://localhost:3000**, create your account, add an RSS feed, start
swiping. Database migrations, the Miniflux admin user, and Miniflux's API key
are all provisioned automatically on the first boot — no UI step.

> **RAM note (Smart Match).** Smart Match embeds articles with a local model
> (Qwen3-Embedding-0.6B) inside the refresh worker — budget **~1.5 GB of
> additional RAM** for that container when the `embeddings` extra is installed.
> The model loads lazily on the first enrichment, never in the API process, and
> unloads between runs. Leave the extra out and the feed still works on keyword
> scoring alone.
>
> **Upgrading an existing install to the pgvector image:** the Postgres
> image changed from `postgres:17-alpine` to `pgvector/pgvector:pg17`
> (glibc). On a pre-existing data volume, run `REINDEX DATABASE niouzou;`
> and `REINDEX DATABASE miniflux;` once after the first boot — text-index
> collation order differs between musl and glibc.

---

## Deploy on Railway

Click the button above. It deploys the whole stack in one shot — **5 services**:
`api`, `pwa`, `miniflux`, `refresh-worker` and `Postgres`. Railway generates
`JWT_SECRET` for you at deploy time; the only optional input is
`OPENROUTER_API_KEY` (enables LLM summaries + keyword scoring). Niouzou
provisions its own Miniflux access token on first boot — no manual key step
(see "How Miniflux integration works" below).

**Shared Postgres, two databases.** The API and Miniflux share **one** Postgres
service but sit in **two databases** on it (the API's default DB and `miniflux`)
so their `users` tables don't collide. The API's `preDeployCommand` creates the
`miniflux` database and runs Alembic on first boot; the template points
Miniflux's `DATABASE_URL` at the `miniflux` database:

```
postgres://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:${{Postgres.PGPORT}}/miniflux?sslmode=disable
```

The API keeps Railway's default `${{Postgres.DATABASE_URL}}` — it points at the
default database, which is where Alembic runs.

**How Miniflux integration works.** Because both apps share the same Postgres,
the API/worker read (or create) a Miniflux access token directly from its
`api_keys` table on first call — see `api/niouzou/services/miniflux_bootstrap.py`.
The token is generated with `secrets.token_hex(32)`, INSERTed with
`description='niouzou'` (`ON CONFLICT DO UPDATE`), and cached in memory.
Idempotent across deploys.

---

## How the scoring works

Two independent relevance scores per article, both computed at ingestion and
persisted side by side (`article_relevance_scores`):

1. **Keyword score** — an LLM (via OpenRouter) extracts weighted keywords from
   each article. Every like/dislike updates your personal keyword weights in
   real time (with decay), and new articles are scored against them before they
   reach your feed.
2. **Smart Match score** — a local embedding model maps each article to a
   1024-dim vector in `pgvector`; the score is a k-NN vote over your liked and
   disliked history. No keywords, no API key.

`SCORING_MODE` (`keyword` — the default — or `smart`) picks which score filters
and ranks the feed; flipping is instant, no re-scoring. `RANDOM_SURFACE_RATE`
injects a few low-score articles so you never fully seal the bubble.

Nothing is hidden: open the Keywords tab to read and edit every weight, or pin
keywords to bias either engine.

---

## Configuration

The values you actually edit in `.env`:

| Variable | Default | What it does |
|---|---|---|
| `JWT_SECRET` | — | **Required.** Long random string used to sign auth tokens. |
| `POSTGRES_PASSWORD` | `niouzou` | App database password — change it. |
| `MINIFLUX_ADMIN_PASSWORD` | `adminpassword` | RSS admin password — change it. |
| `OPENROUTER_API_KEY` | — | Set to enable LLM summaries + keyword extraction. |
| `OPENROUTER_MODEL` | a free model | Any OpenRouter model id — swap it freely. |
| `SCORING_MODE` | `keyword` | Which score drives the feed: `keyword` or `smart` (Smart Match). |
| `SCORE_THRESHOLD` | `0.0` | Minimum relevance score required to surface an article. |
| `RANDOM_SURFACE_RATE` | `0.05` | Share of random low-score articles (anti-bubble). |
| `FEED_GRAVITY` | `1.5` | How fast older articles drop in ranking. |

Full reference in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#environment-variables).

---

## Development

Hot-reload setups (running the API and PWA outside Docker) are documented in
[`api/README.md`](api/README.md) and [`pwa/README.md`](pwa/README.md). The
pytest suite uses a throwaway Postgres:

```bash
docker-compose -f docker-compose.test.yml up -d
DATABASE_URL=postgresql://niouzou:niouzou@localhost:5433/niouzou_test \
    uv run --project api alembic upgrade head
DATABASE_URL=postgresql://niouzou:niouzou@localhost:5433/niouzou_test \
    uv run --project api pytest
```

Architecture, data model, API spec and conventions all live in [`docs/`](docs/).

---

## Known limitations (MVP)

Conscious trade-offs, not bugs — most are harmless for single-user self-hosting:

- **Refresh tokens are not revocable.** JWTs are stateless, valid for 30 days,
  no blacklist. Logout or rotation can't invalidate a token before it expires.
- **Relevance scores are frozen at enrichment.** A user who signs up after an
  article was enriched won't see it in their feed.
- **`RANDOM_SURFACE_RATE` + pagination.** With `SCORE_THRESHOLD > 0`, feed
  pages can be unstable. With the default `SCORE_THRESHOLD = 0.0`, the feed
  is fully deterministic.

---

## Roadmap

**Shipped:** swipe feed with live keyword learning · installable PWA · RSS
ingestion via Miniflux · LLM enrichment (summaries + keywords) · dual scoring
(keyword weights + local Smart Match embeddings) · admin panel · full-text
Explore search · per-user recommendation reset · one-click Railway deploy.

**Exploring:** revocable sessions · re-scoring older articles for users who join
late · richer source management.

The detailed build history lives in the internal development log,
[`docs/EPICS.md`](docs/EPICS.md) — a decision record, not required reading.

---

## Licence

Apache 2.0 + Commons Clause. Free to use, modify, and self-host for personal
or internal use. **Commercial hosting** as a service for third parties is not
permitted. See [`LICENSE`](LICENSE).
