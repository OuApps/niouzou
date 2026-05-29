# Niouzou

**Take back control of your feed.**

A self-hostable news reader with a swipe interface. Every article gets a
relevance score (0–100%) that updates from your likes and dislikes — your
feed gets smarter as you swipe.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/OuApps/niouzou)
![Licence](https://img.shields.io/badge/licence-Apache%202.0%20%2B%20Commons%20Clause-blue)

| | | | |
|---|---|---|---|
| ![Feed](docs/assets/screen_1.png) | ![Article detail](docs/assets/screen_2.png) | ![Saved](docs/assets/screen_3.png) | ![Keywords](docs/assets/screen_4.png) |

- 🔒 **Your data, your server** — runs anywhere Docker runs
- 🧠 **Learns from your swipes** — keyword weights you can inspect and edit
- 📱 **Installable PWA** — swipe, save for later, no app store
- ⚡ **AI optional** — TF-IDF works fine; add an OpenRouter key for LLM summaries

---

## Self-hosting

You need Docker. That's it.

```bash
git clone https://github.com/yourname/niouzou.git && cd niouzou
cp .env.example .env && $EDITOR .env       # set JWT_SECRET + POSTGRES_PASSWORD
docker compose up -d
```

Open **http://localhost:3000**, create your account, add an RSS feed, start
swiping. Database migrations, the Miniflux admin user, and Miniflux's API key
are all provisioned automatically on the first boot — no UI step.

---

## Deploy on Railway

Click the button above. You need `JWT_SECRET` (use `openssl rand -hex 32`) and,
on Railway only, a `MINIFLUX_API_KEY` you create once in the Miniflux UI.
`OPENROUTER_API_KEY` is optional and enables AI summaries.

**Database setup.** The API and Miniflux share **one** Postgres service but
sit in **two databases** on it (`niouzou` and `miniflux`) so their `users`
tables don't collide. The API's preDeploy step creates the `miniflux`
database automatically on first boot; you just need to point the Miniflux
service at it. In Railway, set the Miniflux service's `DATABASE_URL` to:

```
postgres://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/miniflux?sslmode=disable
```

The API keeps Railway's default `${{Postgres.DATABASE_URL}}` — it points at
the default database, which is where Alembic runs.

---

## How the scoring works

1. Each article is enriched with weighted keywords (LLM or TF-IDF).
2. Every like/dislike updates your personal keyword weights in real time.
3. New articles are scored against your weights before they hit your feed.
4. A small % of low-score articles surfaces randomly — no filter bubble.

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
docker compose -f docker-compose.test.yml up -d
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
- **Miniflux deduplicates feeds globally.** Two users adding the same RSS URL
  end up sharing the first user's source.
- **Relevance scores are frozen at enrichment.** A user who signs up after an
  article was enriched won't see it (a backfill pass is planned).
- **`RANDOM_SURFACE_RATE` + pagination.** With `SCORE_THRESHOLD > 0`, feed
  pages can be unstable. With the default `SCORE_THRESHOLD = 0.0`, the feed
  is fully deterministic.

---

## Roadmap

See [`docs/EPICS.md`](docs/EPICS.md) for the full breakdown.

- [x] EPIC 1–5 — PWA, ingestion, API, scoring, AI enrichment
- [x] EPIC 6 — Packaging & open source
- [ ] EPIC 7 — PWA polish & follow-up

---

## Licence

Apache 2.0 + Commons Clause. Free to use, modify, and self-host for personal
or internal use. **Commercial hosting** as a service for third parties is not
permitted. See [`LICENSE`](LICENSE).
