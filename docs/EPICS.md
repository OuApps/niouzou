# Epics — Niouzou

## Overview

| Epic | Title | Depends on |
|---|---|---|
| EPIC 1 | PWA — UI & navigation | — |
| EPIC 2 | Foundations & ingestion | — |
| EPIC 3 | API & basic scoring | EPIC 2 |
| EPIC 4 | PWA — API integration | EPIC 1, EPIC 3 |
| EPIC 5 | AI enrichment | EPIC 2, EPIC 3 |
| EPIC 6 | Packaging & open source | EPIC 3, EPIC 4, EPIC 5 |

> EPIC 1 and EPIC 2 can be developed in parallel.
> EPIC 1 uses mocked data until EPIC 4 connects it to the real API.

---

## EPIC 1 — PWA: UI & Navigation

**Goal**: Build the complete mobile UI with mocked data. The app must feel production-ready before any backend is connected. UI quality is a go/no-go gate for the rest of the project.

**Reference**: `docs/DESIGN_SYSTEM.md` — must be read before writing any component.

### Stories

#### E1-S1 — Project scaffold
- Vite + React project
- Tailwind CSS configured
- `lucide-react` installed
- Inter font loaded
- PWA manifest configured (`theme_color: #0c1018`, `display: standalone`)
- Animated blob background component (`<BlobBackground />`) implemented and reused across all screens
- React Router configured with all routes

**Routes**:
```
/             → Feed
/articles/:id → Article detail
/saved        → Saved
/keywords     → Keywords
/profile      → Profile
/sources      → Manage sources
/login        → Login
/register     → Register
```

**Acceptance criteria**:
- Blobs animate smoothly at 60fps on mobile
- All routes render without error
- `<BlobBackground />` is identical across all screens

---

#### E1-S2 — Feed screen (mocked)
- Swipeable article cards using `react-spring` + `@use-gesture/react`
- Card structure: og:image (placeholder), source badge, score badge (%), title, summary_short, keyword tags, meta (time ago · read time)
- Swipe right → like (card flies right, cyan tint)
- Swipe left → dislike (card flies left, red tint)
- Swipe up → skip (card flies up)
- Tap card → navigate to `/articles/:id`
- Action buttons (dislike / save / like) trigger same animations as swipe
- Next card appears from below with subtle scale-up animation
- Bottom navigation with 4 tabs

**Mocked data**: hardcode 5–10 articles matching the API response shape from `docs/API_SPEC.md`.

**Acceptance criteria**:
- Swipe animations feel fluid and natural on Android
- Action buttons and swipe gestures produce identical results
- Score badge visible on every card

---

#### E1-S3 — Article detail screen (mocked)
- Full screen: og:image header, source + date, title, summary_executive (bullet points), summary_short, keyword tags, score badge
- "Read full article" button → opens original URL in browser
- Back button → returns to feed
- Like / dislike / save actions accessible from this screen

**Acceptance criteria**:
- `summary_executive` renders as bullet list
- `summary_executive` section hidden gracefully when null
- Save/unsave toggle on bookmark button: filled icon + yellow when saved, outline when not
- Content scrolls so action buttons below the fold are reachable

---

#### E1-S4 — Saved screen (mocked)
- List of saved articles: thumbnail, source, title, score pill, saved timestamp
- Tap row → navigate to `/articles/:id`
- Empty state with friendly message when no saved articles

**Acceptance criteria**:
- Empty state visible and styled consistently
- Saved list updates reactively when articles are saved/unsaved from ArticleDetail

---

#### E1-S5 — Keywords screen (mocked)
- List of keyword rows: term, horizontal bar (positive = cyan right, negative = red left from center), like/dislike counts, edit pencil icon
- Section divider between positive and negative keywords
- Tap pencil → inline weight editor (number input, confirm button)
- Empty state for new users

**Acceptance criteria**:
- Bar direction and color correctly reflect positive vs negative weight
- Inline editor opens and closes without layout shift

---

#### E1-S6 — Profile screen (mocked)
- Avatar with initials + orange/cyan gradient
- Name + email
- Stats row: articles read, liked, sources (mocked numbers)
- Menu: Manage sources → `/sources`, Sign out → `/login`

**Acceptance criteria**:
- Sign out navigates to `/login` and clears any stored auth token

---

#### E1-S7 — Manage sources screen (mocked)
- List of current sources: name, RSS URL, delete button
- "Add source" input: URL field + submit button
- Optimistic UI: source appears immediately in list on submit
- Delete with confirmation

**Acceptance criteria**:
- Add and delete work against mocked state
- URL validation (must start with `http`)

---

#### E1-S8 — Login & Register screens
- Login: email + password + submit → stores fake JWT in localStorage → redirects to `/`
- Register: email + password + confirm password → same flow
- Link between login and register screens
- Form validation (empty fields, password mismatch)

**Acceptance criteria**:
- All form errors shown inline, not as alerts
- Redirect works after fake login

---

## EPIC 2 — Foundations & Ingestion

**Goal**: PostgreSQL schema deployed, Miniflux running, `cron_fetch` pulling articles into Niouzou DB.

### Stories

#### E2-S1 — PostgreSQL schema
- Deploy PostgreSQL on Railway
- Run migrations for all tables defined in `docs/DATA_MODEL.md`
- Migration tool: Alembic

**Tables**: `users`, `sources`, `articles`, `article_keywords`, `article_relevance_scores`, `article_impressions`, `article_feedbacks`, `keyword_weights`

**Acceptance criteria**:
- All tables created with correct types, constraints, and indexes
- Alembic migration runs cleanly from zero

---

#### E2-S2 — Miniflux setup
- Deploy Miniflux on Railway using official Docker image
- Configure Miniflux admin credentials via env vars
- Generate Miniflux API key
- Verify Miniflux REST API is reachable from the API service

**Acceptance criteria**:
- Miniflux UI accessible
- At least one RSS feed added manually and pulling articles

---

#### E2-S3 — `cron_fetch`
- Python module `niouzou.crons.fetch`
- Pulls new entries from Miniflux REST API (`GET /v1/entries?status=unread`)
- Inserts new articles into `articles` table with `status = pending`
- Deduplication via `miniflux_entry_id` (upsert, skip if exists)
- Marks entries as read in Miniflux after ingestion

**Acceptance criteria**:
- Running `cron_fetch` twice does not create duplicate articles
- New articles appear in DB within one run after being published in Miniflux

---

## EPIC 3 — API & Basic Scoring

**Goal**: FastAPI server running, all endpoints from `docs/API_SPEC.md` implemented, TF-IDF scoring pipeline active.

### Stories

#### E3-S1 — FastAPI project structure
- FastAPI app with folder structure:
```
api/
  niouzou/
    routers/       ← one file per resource (feed, articles, feedback, sources, keywords, auth)
    services/      ← business logic layer
    models/        ← SQLAlchemy models
    schemas/       ← Pydantic schemas
    scoring/       ← BaseScorer, TFIDFScorer, ScoringPipeline
    crons/         ← fetch, enrich, refresh_weights
    db.py
    config.py      ← settings from env vars
    main.py
```

**Acceptance criteria**:
- App starts cleanly, `/health` returns 200

---

#### E3-S2 — Authentication
- `POST /auth/register` and `POST /auth/login`
- JWT via `python-jose`, passwords hashed via `passlib[bcrypt]`
- `POST /auth/refresh`
- Auth middleware applied to all protected routes

**Acceptance criteria**:
- Register → login → access protected endpoint works end to end
- Expired token returns 401

---

#### E3-S3 — Sources endpoints
- `GET /sources`, `POST /sources`, `DELETE /sources/:id`
- `POST /sources` registers feed in Miniflux via its API, then inserts into `sources` table
- Returns 409 if URL already exists for user

**Acceptance criteria**:
- Adding a source triggers Miniflux feed creation
- Deleting a source does not delete existing articles

---

#### E3-S4 — TF-IDF scoring pipeline
- `TFIDFScorer` extracts keywords with salience scores from article content
- `ScoringPipeline` runs active scorers and normalises output to 0.0–1.0 (`relevance_score`)
- Unknown keywords → weight 0 (neutral)
- Score computed per user at enrichment time, stored in `article_relevance_scores`

**Acceptance criteria**:
- New user sees all articles (all scores neutral → all pass threshold)
- After likes/dislikes, scores reflect keyword weights correctly

---

#### E3-S5 — Feed endpoint
- `GET /feed` with cursor-based pagination
- HN-style ranking: `feed_rank = relevance_score / (age_in_hours + 2) ^ FEED_GRAVITY`
- Excludes articles with an impression for this user
- Applies `SCORE_THRESHOLD` and `RANDOM_SURFACE_RATE`

**Acceptance criteria**:
- Cursor pagination returns non-overlapping pages
- Already-seen articles never reappear

---

#### E3-S6 — Feedback endpoint + synchronous weight update
- `POST /feedback` upserts `article_feedbacks`
- Synchronously recomputes `keyword_weights` for affected terms (row-level lock)
- `save` counts as `+1` like for weight computation
- Idempotent: like×4 = like×1

**Acceptance criteria**:
- Changing action (like → dislike) correctly updates weight
- Concurrent feedback calls do not corrupt weights

---

#### E3-S7 — Remaining endpoints
- `POST /feed/:id/impression`
- `GET /articles/:id`
- `GET /saved`
- `GET /keywords`, `PATCH /keywords/:term`

**Acceptance criteria**:
- All endpoints match shapes defined in `docs/API_SPEC.md`

---

#### E3-S8 — `cron_refresh_weights`
- Daily full recompute of all `keyword_weights` from all `article_feedbacks`
- Skips rows with `manually_overridden = true`
- Does not touch `article_relevance_scores`

**Acceptance criteria**:
- Running cron twice produces identical results (idempotent)
- Manually overridden weights are preserved

---

## EPIC 4 — PWA: API Integration

**Goal**: Replace all mocked data in the PWA with real API calls.

### Stories

#### E4-S1 — API client & auth
- Axios (or fetch) client with base URL from env var `VITE_API_URL`
- JWT stored in localStorage, attached to all requests via interceptor
- 401 response → redirect to `/login`
- Token refresh flow

---

#### E4-S2 — Feed integration
- `GET /feed` with infinite scroll (load next page on last card)
- `POST /feed/:id/impression` called as card is displayed
- Swipe/button actions call `POST /feedback`
- Optimistic UI: card dismissed immediately, feedback sent in background

---

#### E4-S3 — Saved, Keywords, Profile, Sources integration
- Replace all mocked state with real API calls
- Loading states and error states for all screens
- Pull-to-refresh on Saved screen

**Acceptance criteria**:
- All screens functional end-to-end with real data
- Network errors shown with friendly inline messages (no raw JSON)

---

## EPIC 5 — AI Enrichment

**Goal**: `cron_enrich` calls OpenRouter to generate summaries and extract keywords. Scoring pipeline switches to `AIKeywordScorer` when key is present.

> **Already scaffolded in Epic 3** (do not rebuild — wire into these):
> - `niouzou.scoring` is complete: `BaseScorer`, `TFIDFScorer` (working extraction + scoring), `ScoringPipeline` (config-based scorer selection + 0.0–1.0 sigmoid normalisation), unit-tested.
> - `niouzou.scoring.ai_keyword.AIKeywordScorer` exists as a **stub**: its `score()` is inherited and works; only `extract_keywords()` raises `NotImplementedError` — that body is E5-S3. The pipeline *already selects it* when `OPENROUTER_API_KEY` is set.
> - `niouzou.services.scoring_service.ScoringService` is the DB bridge: `extract_and_store_keywords(article)` (writes `article_keywords`) and `score_article_for_user(article_id, user_id)` (writes `article_relevance_scores`). `cron_enrich` must call these — the scoring/persistence logic is NOT to be reimplemented in the cron.

### Stories

#### E5-S1 — `cron_enrich` — content extraction
- `newspaper4k` fetches and extracts clean content from article URL
- Fallback to RSS content if fetch fails
- Stores extracted content in `articles.content`

> **From Epic 3**: after content is stored, the no-AI path calls
> `ScoringService.extract_and_store_keywords` then `score_article_for_user`
> (per user) — both already implemented and tested.

---

#### E5-S2 — `cron_enrich` — LLM enrichment
- If `OPENROUTER_API_KEY` set: call OpenRouter with `OPENROUTER_MODEL`
- Generate `summary_short` (3 engaging sentences)
- Generate `summary_executive` (bullet points)
- Extract keywords with salience as JSON: `[{"term": "rust", "salience": 0.9}]`
- Store in `articles` and `article_keywords`
- Set `articles.enriched_at`, `articles.status = enriched`

**Acceptance criteria**:
- LLM output parsed as JSON without error
- Malformed LLM response retried once, then falls back to TF-IDF

> **Open item for Epic 5**: scoring is per-user and frozen at enrichment, so the
> cron must loop over the article's relevant users when writing
> `article_relevance_scores`. A user who registers *after* an article was
> enriched has no score for it and won't see it in their feed — decide whether
> Epic 5 needs a backfill pass for new users / pre-existing articles.

---

#### E5-S3 — `AIKeywordScorer`
- Replaces `TFIDFScorer` when `OPENROUTER_API_KEY` is present
- Uses LLM-extracted keyword salience × user `keyword_weights`
- `ScoringPipeline` auto-selects correct scorer based on config

> **From Epic 3**: selection logic and `score()` already done. This story is
> just implementing `AIKeywordScorer.extract_keywords()` (currently raises
> `NotImplementedError`) to parse the LLM JSON into `ScoredKeyword`s.

**Acceptance criteria**:
- Switching `OPENROUTER_API_KEY` on/off changes active scorer
- Score output range remains 0.0–1.0

---

## EPIC 6 — Packaging & Open Source

**Goal**: Anyone can self-host Niouzou with a single `docker compose up`. Repository published on GitHub under Apache 2.0 + Commons Clause.

### Stories

#### E6-S1 — Docker images
- `Dockerfile` for API (also used for cron jobs)
- `Dockerfile` for PWA (Nginx serving Vite build)
- Images optimised (multi-stage builds, minimal base images)

> **Note from Epic 3**: `bcrypt` is pinned to `4.0.1` in `pyproject.toml` (to suppress a passlib warning). Verify this version builds cleanly in the Docker image — it installs fine locally on Python 3.14 arm64 but has not been tested in a container yet.

---

#### E6-S2 — Docker Compose
- `docker-compose.yml` at repo root
- Services: `postgres`, `miniflux`, `api`, `pwa`, `cron_fetch`, `cron_enrich`, `cron_refresh_weights`
- All config via `.env` (template: `.env.example`)
- Cron jobs use `restart: unless-stopped` with sleep loops
- One-shot `migrate` service (same image as `api`, `command: alembic upgrade head`, `restart: "no"`); `api` and cron services depend on it via `depends_on: condition: service_completed_successfully` so migrations run exactly once before the app starts
- Add a dedicated test database service (e.g. `postgres-test`) so `pytest` never runs against the dev/prod database. `conftest.py` currently TRUNCATEs 8 tables at the start of every DB test — running it against a database with real data would destroy it.

**Acceptance criteria**:
- `docker compose up` from a clean machine starts all services
- Alembic migrations run automatically once (via the `migrate` service) before `api` accepts traffic
- App accessible at `localhost:3000`
- `pytest` targets the test database, not the dev database

---

#### E6-S3 — Railway config
- `railway.toml` declaring all services
- API service runs `alembic upgrade head` as its pre-deploy / release command, so migrations apply once per deploy (after build, before the new version takes traffic) — never at per-replica startup
- "Deploy on Railway" button in README
- Env var documentation per service

---

#### E6-S4 — Repository & licence
- GitHub repository published
- `LICENSE` file: Apache 2.0 + Commons Clause
- `README.md`: what is Niouzou, self-hosting quickstart, Railway deploy button, env var reference, screenshot
- `docs/` folder committed with all architecture documents
- README must document the following known MVP limitations:
  - **Refresh tokens non-revocable**: JWTs are stateless, valid for 30 days, no blacklist. A logout or compromised token cannot be invalidated before expiry.
  - **Miniflux feed deduplication is global**: if two users add the same RSS URL, Miniflux deduplicates at the feed level — the second `POST /sources` may return an error or the existing feed. Articles from a shared feed are only ingested under the first user's source. Harmless in single-user setups.
  - **Relevance scores frozen at enrichment**: a user who registers after an article was enriched has no `relevance_score` for it and will never see it in their feed (unless a backfill is run — see Epic 5 open item).
  - **`RANDOM_SURFACE_RATE` + keyset pagination**: with `SCORE_THRESHOLD > 0`, the random branch is re-evaluated on every request, so pages may be unstable. With the default `SCORE_THRESHOLD = 0.0`, the feed is 100% deterministic.

**Acceptance criteria**:
- README self-hosting instructions tested on a clean machine
- Licence file present and correct