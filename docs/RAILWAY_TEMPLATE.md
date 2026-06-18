# Deploy and Host Niouzou on Railway

Niouzou is a self-hostable, mobile-first news aggregator with a swipe interface.
You swipe through articles; the system learns your preferences from your likes
and dislikes and surfaces only what's relevant. Every article gets a relevance
score (0–100%) that updates as you swipe — your feed gets smarter the more you
use it.

## About Hosting Niouzou

Hosting Niouzou runs five coordinated services: a FastAPI backend, a React PWA,
a Miniflux RSS reader, a background refresh worker (RSS fetch + LLM enrichment +
local embeddings), and a PostgreSQL database with the pgvector extension. The
API and Miniflux share one Postgres instance across two databases; the API
auto-provisions the Miniflux schema, admin user, and access token on first boot,
and runs its own migrations from a pre-deploy step. This template wires all five
services together so the stack comes up ready to swipe — no manual key step.

## Why Deploy Niouzou on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will
host your infrastructure so you don't have to deal with configuration, while
allowing you to vertically and horizontally scale it.

By deploying Niouzou on Railway, you are one step closer to supporting a
complete full-stack application with minimal burden. Host your servers,
databases, AI agents, and more on Railway.

Niouzou is a multi-service app (API, PWA, RSS reader, worker, database).
Railway's private networking, shared Postgres, and one-click multi-service
templates make it a natural fit: the whole stack deploys together, `JWT_SECRET`
is generated for you, and the only optional input is an OpenRouter API key for
AI summaries.

## Common Use Cases

- A private, self-hosted replacement for algorithmic news feeds — your data and
  reading habits stay on your own server.
- A personalized RSS reader that learns what you care about and filters the noise.
- A self-hosted reading inbox: swipe to triage, save articles for later, and
  full-text search across your sources.

## Dependencies for Niouzou Hosting

- **PostgreSQL with pgvector** — application data, learned preferences, and
  article embeddings.
- **Miniflux** — RSS/Atom ingestion (its own service, sharing the Postgres
  instance).
- **OpenRouter** (optional) — LLM summaries and keyword extraction; without it
  the feed still works on local Smart Match embeddings.

### Deployment Dependencies

- [Niouzou source repository](https://github.com/OuApps/niouzou)
- [Miniflux](https://miniflux.app/) — RSS reader
- [pgvector](https://github.com/pgvector/pgvector) — Postgres vector extension
- [OpenRouter](https://openrouter.ai/) (optional) — LLM provider

### Implementation Details

The API and Miniflux share one Postgres service across two databases (the API's
default database and `miniflux`) so their `users` tables don't collide. The
API's pre-deploy command creates the `miniflux` database and runs Alembic
migrations; the Miniflux service points its `DATABASE_URL` at the `miniflux`
database. The refresh worker loads a local embedding model
(Qwen3-Embedding-0.6B) lazily and unloads it between runs to keep idle RAM low.
