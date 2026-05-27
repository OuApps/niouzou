# Niouzou API

Python 3.11 / FastAPI backend. Python and dependencies are managed with
[`uv`](https://docs.astral.sh/uv/).

## Setup

```bash
cd api
uv python install 3.11   # uv manages the interpreter (see .python-version)
uv sync                  # create .venv and install deps (incl. dev group)
```

Configuration comes from environment variables (see `../.env.example`). The
only required vars for Epic 2 are `DATABASE_URL`, `MINIFLUX_URL`,
`MINIFLUX_API_KEY`.

## Local dev stack (Postgres + Miniflux)

```bash
docker-compose -f docker-compose.dev.yml up -d
# Postgres → localhost:5432, Miniflux UI/API → localhost:8080
```

## Database migrations (Alembic)

```bash
uv run alembic upgrade head          # apply all migrations
uv run alembic downgrade base        # tear down
uv run alembic revision --autogenerate -m "..."   # new migration from models
uv run alembic check                 # fail if models drift from the DB
```

## cron_fetch

Pulls unread entries from Miniflux into the `articles` table (status=pending),
deduplicating on `miniflux_entry_id`, then marks them read in Miniflux.

```bash
uv run python -m niouzou.crons.fetch
```

A Niouzou `source` row must exist with the matching `miniflux_feed_id` for an
entry to be ingested (sources are created via the API in Epic 3). Entries whose
feed has no registered source are left unread and logged.

## Tests

```bash
uv run pytest
```

The Miniflux client tests are pure (HTTP mocked with `respx`). The `cron_fetch`
tests need the dev Postgres running and skip cleanly otherwise.
