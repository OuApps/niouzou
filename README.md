# Niouzou

**Take back control of your feed.**

A self-hostable news reader with a swipe interface. Every article gets a
relevance score (0–100%) that updates from your likes and dislikes — your
feed gets smarter as you swipe.

[![CI](https://github.com/OuApps/niouzou/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/OuApps/niouzou/actions/workflows/ci.yml)
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/niouzou?referralCode=bGgJYu)
![Licence](https://img.shields.io/badge/licence-Apache%202.0%20%2B%20Commons%20Clause-blue)

![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white)

| | | | |
|---|---|---|---|
| ![Feed](docs/assets/screen_1.png) | ![Explore & search](docs/assets/screen_2.png) | ![Saved](docs/assets/screen_3.png) | ![Keywords](docs/assets/screen_4.png) |

- 🔒 **Your data, your server** — runs anywhere Docker runs
- 🧠 **Learns from your swipes** — keyword weights you can inspect and edit
- 📱 **Installable PWA** — swipe, save for later, no app store
- ⚡ **AI optional** — semantic Smart Match scoring runs on a local model; add an OpenRouter key for LLM summaries + keyword scoring

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

Niouzou keeps **two independent relevance scores** for every article, both
computed when the article is ingested:

1. **Keyword score** — an LLM enriches each article with weighted keywords.
   Every like/dislike updates your personal keyword weights in real time, and
   new articles are scored against them before they reach your feed.
2. **Smart Match score** — a local embedding model places each article in
   semantic space and scores it by similarity to what you've liked (k-NN). No
   keywords, no AI key required.

You choose which score drives the feed with `SCORING_MODE` (`keyword` — the
default — or `smart`); flipping it is instant, no re-scoring. A small % of
low-score articles surfaces randomly either way — no filter bubble.

No black box. Inspect and edit every keyword weight in the Keywords tab.

---

## Configuration

The values you actually edit in `.env`:

| Variable | Default | What it does |
|---|---|---|
| `JWT_SECRET` | — | **Required.** Long random string used to sign auth tokens. |
| `POSTGRES_PASSWORD` | `niouzou` | App database password — change it. |
| `MINIFLUX_ADMIN_PASSWORD` | `adminpassword` | RSS admin password — change it. |
| `OPENROUTER_API_KEY` | — | Set to enable LLM summaries + keyword extraction. |
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
