# Epics — Niouzou

> **Internal development log / decision record.** This file is the project's
> chronological build log — the design decisions, trade-offs and acceptance
> notes behind each story. It is *not* the public roadmap: for what Niouzou does
> today and where it's going, see the **Roadmap** section of the
> [README](../README.md). Contributors only need the focused docs in this
> folder (`ARCHITECTURE`, `API_SPEC`, `DATA_MODEL`, `CONVENTIONS`); this log is
> here for history, not as required reading.

## Overview

| Epic | Title | Depends on |
|---|---|---|
| EPIC 1 | PWA — UI & navigation | — |
| EPIC 2 | Foundations & ingestion | — |
| EPIC 3 | API & basic scoring | EPIC 2 |
| EPIC 4 | PWA — API integration | EPIC 1, EPIC 3 |
| EPIC 5 | AI enrichment | EPIC 2, EPIC 3 |
| EPIC 6 | Packaging & open source | EPIC 3, EPIC 4, EPIC 5 |
| EPIC 7 | PWA polish & follow-up | EPIC 4 |
| EPIC 8 | Admin panel | EPIC 3, EPIC 4 |
| EPIC 9 | Refonte UX TikTok-like | EPIC 3, EPIC 4, EPIC 5 |
| EPIC 10 | Scaling | EPIC 5 |
| EPIC 11 | Filtres Explore | EPIC 9, EPIC 10 |
| EPIC 12 | ~~Robustesse des keywords~~ (remplacée par EPIC 16) | EPIC 5, EPIC 9 |
| EPIC 16 | Smart Match — scoring sémantique par embeddings | EPIC 5, EPIC 9, EPIC 10 |
| EPIC 21 | Chat IA sur un article (bottom sheet) | EPIC 5, EPIC 9 |
| EPIC 22 | Serveur MCP + clés service account | EPIC 3, EPIC 8, EPIC 9 |
| EPIC 24 | Tags de sources & mode Loupe | EPIC 9, EPIC 11 |

> EPIC 1 and EPIC 2 can be developed in parallel.
> EPIC 1 uses mocked data until EPIC 4 connects it to the real API.

---

## EPIC 1 — PWA: UI & Navigation

**Goal**: Build the complete mobile UI with mocked data. The app must feel production-ready before any backend is connected. UI quality is a go/no-go gate for the rest of the project.

**Reference**: `docs/DESIGN_SYSTEM.md` — must be read before writing any component.

### Stories

#### [x] E1-S1 — Project scaffold
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

#### [x] E1-S2 — Feed screen (mocked)
- Swipeable article cards using `react-spring` + `@use-gesture/react`
- Card structure: og:image (placeholder), source badge, score badge (%), title, summary_short, keyword tags, meta (time ago · read time)
- Swipe right → like (card flies right, cyan tint)
- Swipe left → dislike (card flies left, red tint)
- Swipe up → skip (card flies up, neutral — article dismissed without feedback)
- Swipe down → save (card flies down, yellow tint)
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

#### [x] E1-S3 — Article detail screen (mocked)
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

#### [x] E1-S4 — Saved screen (mocked)
- List of saved articles: thumbnail, source, title, score pill, saved timestamp
- Tap row → navigate to `/articles/:id`
- Empty state with friendly message when no saved articles

**Acceptance criteria**:
- Empty state visible and styled consistently
- Saved list updates reactively when articles are saved/unsaved from ArticleDetail

---

#### [x] E1-S5 — Keywords screen (mocked)
- List of keyword rows: term, horizontal bar (positive = cyan right, negative = red left from center), like/dislike counts, edit pencil icon
- Section divider between positive and negative keywords
- Tap pencil → inline weight editor (number input, confirm button)
- Empty state for new users

**Acceptance criteria**:
- Bar direction and color correctly reflect positive vs negative weight
- Inline editor opens and closes without layout shift

---

#### [x] E1-S6 — Profile screen (mocked)
- Avatar with initials + orange/cyan gradient
- Name + email
- Stats row: articles read, liked, sources (mocked numbers)
- Menu: Manage sources → `/sources`, Sign out → `/login`

**Acceptance criteria**:
- Sign out navigates to `/login` and clears any stored auth token

---

#### [x] E1-S7 — Manage sources screen (mocked)
- List of current sources: name, RSS URL, delete button
- "Add source" input: URL field + submit button
- Optimistic UI: source appears immediately in list on submit
- Delete with confirmation

**Acceptance criteria**:
- Add and delete work against mocked state
- URL validation (must start with `http`)

---

#### [x] E1-S8 — Login & Register screens
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

#### [x] E2-S1 — PostgreSQL schema
- Deploy PostgreSQL on Railway
- Run migrations for all tables defined in `docs/DATA_MODEL.md`
- Migration tool: Alembic

**Tables**: `users`, `sources`, `articles`, `article_keywords`, `article_relevance_scores`, `article_impressions`, `article_feedbacks`, `keyword_weights`

**Acceptance criteria**:
- All tables created with correct types, constraints, and indexes
- Alembic migration runs cleanly from zero

---

#### [x] E2-S2 — Miniflux setup
- Deploy Miniflux on Railway using official Docker image
- Configure Miniflux admin credentials via env vars
- Generate Miniflux API key
- Verify Miniflux REST API is reachable from the API service

**Acceptance criteria**:
- Miniflux UI accessible
- At least one RSS feed added manually and pulling articles

---

#### [x] E2-S3 — `cron_fetch`
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

#### [x] E3-S1 — FastAPI project structure
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

#### [x] E3-S2 — Authentication
- `POST /auth/register` and `POST /auth/login`
- JWT via `python-jose`, passwords hashed via `passlib[bcrypt]`
- `POST /auth/refresh`
- Auth middleware applied to all protected routes

**Acceptance criteria**:
- Register → login → access protected endpoint works end to end
- Expired token returns 401

---

#### [x] E3-S3 — Sources endpoints
- `GET /sources`, `POST /sources`, `DELETE /sources/:id`
- `POST /sources` registers feed in Miniflux via its API, then inserts into `sources` table
- Returns 409 if URL already exists for user

**Acceptance criteria**:
- Adding a source triggers Miniflux feed creation
- Deleting a source does not delete existing articles

---

#### [x] E3-S4 — TF-IDF scoring pipeline
- `TFIDFScorer` extracts keywords with salience scores from article content
- `ScoringPipeline` runs active scorers and normalises output to 0.0–1.0 (`relevance_score`)
- Unknown keywords → weight 0 (neutral)
- Score computed per user at enrichment time, stored in `article_relevance_scores`

**Acceptance criteria**:
- New user sees all articles (all scores neutral → all pass threshold)
- After likes/dislikes, scores reflect keyword weights correctly

---

#### [x] E3-S5 — Feed endpoint
- `GET /feed` with cursor-based pagination
- HN-style ranking: `feed_rank = relevance_score / (age_in_hours + 2) ^ FEED_GRAVITY`
- Excludes articles with an impression for this user
- Applies `SCORE_THRESHOLD` and `RANDOM_SURFACE_RATE`

**Acceptance criteria**:
- Cursor pagination returns non-overlapping pages
- Already-seen articles never reappear

---

#### [x] E3-S6 — Feedback endpoint + synchronous weight update
- `POST /feedback` upserts `article_feedbacks`
- Synchronously recomputes `keyword_weights` for affected terms (row-level lock)
- `save` counts as `+1` like for weight computation
- Idempotent: like×4 = like×1

**Acceptance criteria**:
- Changing action (like → dislike) correctly updates weight
- Concurrent feedback calls do not corrupt weights

---

#### [x] E3-S7 — Remaining endpoints
- `POST /feed/:id/impression`
- `GET /articles/:id`
- `GET /saved`
- `GET /keywords`, `PATCH /keywords/:term`

**Acceptance criteria**:
- All endpoints match shapes defined in `docs/API_SPEC.md`

---

#### [x] E3-S8 — `cron_refresh_weights`
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

#### [x] E4-S1 — API client & auth
- Axios (or fetch) client with base URL from env var `VITE_API_URL`
- JWT stored in localStorage, attached to all requests via interceptor
- 401 response → redirect to `/login`
- Token refresh flow

---

#### [x] E4-S2 — Feed integration
- `GET /feed` with infinite scroll (load next page on last card)
- `POST /feed/:id/impression` called as card is displayed
- Swipe/button actions call `POST /feedback`
- Optimistic UI: card dismissed immediately, feedback sent in background

---

#### [x] E4-S3 — Saved, Keywords, Profile, Sources integration
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

#### [x] E5-S1 — `cron_enrich` — content extraction
- `newspaper4k` fetches and extracts clean content from article URL
- Fallback to RSS content if fetch fails
- Stores extracted content in `articles.content`

> **From Epic 3**: after content is stored, the no-AI path calls
> `ScoringService.extract_and_store_keywords` then `score_article_for_user`
> (per user) — both already implemented and tested.

---

#### [x] E5-S2 — `cron_enrich` — LLM enrichment
- If `OPENROUTER_API_KEY` set: call OpenRouter with `OPENROUTER_MODEL`
- Generate `summary_short` (2 engaging sentences to hook the reader)
- Generate `summary_executive` (3-5 markdown bullet points)
- Extract keywords with salience as JSON: `[{"term": "rust", "salience": 0.9}]`
  - Keywords extracted from full article content (after `newspaper4k` extraction or RSS fallback)
  - Inject existing vocabulary (top ~200 most-frequent keywords from the DB) to orient the LLM toward coherent terms
  - Request 3-4 broad categories (e.g., "Science", "Sports", "Politics") and 3-4 specific entity keywords (e.g., person names, company names, places)
  - Capped at 10 keywords; excess low-salience keywords trimmed post-generation
- Store in `articles` and `article_keywords`
- Set `articles.enriched_at`, `articles.status = enriched`

**Acceptance criteria**:
- LLM output parsed as JSON without error
- Malformed LLM response retried once (up to 3 total attempts with backoff), then falls back to TF-IDF
- Keywords extracted from the full article content, not just the summary
- Injected vocabulary bias guides the LLM toward existing keywords when applicable
- Keywords lean toward 3-4 general + 3-4 specific to improve coherence and accumulation

> **Open item for Epic 5**: scoring is per-user and frozen at enrichment, so the
> cron must loop over the article's relevant users when writing
> `article_relevance_scores`. A user who registers *after* an article was
> enriched has no score for it and won't see it in their feed — decide whether
> Epic 5 needs a backfill pass for new users / pre-existing articles.

---

#### [x] E5-S3 — `AIKeywordScorer`
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

## EPIC 6 — Packaging & Open Source ✅

**Goal**: Anyone can self-host Niouzou with a single `docker compose up`. Repository published on GitHub under the GNU AGPL-3.0 (relicensed from Apache 2.0 + Commons Clause in E18).

### Stories

#### [x] E6-S1 — Docker images ✅
- `api/Dockerfile` — multi-stage, uv-based, slim Python 3.13 base. Serves the
  API, the `migrate` one-shot, and the three cron jobs.
- `pwa/Dockerfile` — multi-stage, Node 22 build → Nginx 1.27 alpine static serve
  with SPA fallback (`pwa/nginx.conf`). `VITE_API_URL` is consumed as a build
  ARG because Vite inlines it at build time.
- Both Dockerfiles build with the legacy builder (no BuildKit-only syntax), so
  self-hosters don't need buildx installed.
- `bcrypt 4.0.1` builds and imports cleanly in the runtime image (lxml needs
  `libxml2`/`libxslt`/`zlib` build deps, added to the builder stage).

---

#### [x] E6-S2 — Docker Compose ✅
- `docker-compose.yml` at repo root.
- Services: `postgres`, `miniflux`, `migrate`, `api`, `pwa`,
  `cron_fetch`, `cron_enrich`, `cron_refresh_weights`.
- **A single Postgres instance hosts both the `niouzou` and `miniflux`
  databases.** The `infra/postgres-init/01-miniflux.sh` script creates the
  `miniflux` user and database the first time the volume is initialised.
- All config via `.env` (template: `.env.example`).
- Cron jobs use `restart: unless-stopped` with sleep loops driven by
  `CRON_*_INTERVAL` env vars.
- One-shot `migrate` service (same image as `api`, `command: alembic upgrade head`,
  `restart: "no"`); `api` and cron services depend on it via
  `depends_on: condition: service_completed_successfully`.
- Miniflux admin account provisioned via `MINIFLUX_ADMIN_USERNAME` /
  `MINIFLUX_ADMIN_PASSWORD` ([Miniflux env-based admin creation](https://miniflux.app/docs/configuration.html#create-admin-user)).
- **Miniflux API token auto-provisioned at runtime.** Miniflux exposes no HTTP
  endpoint to mint API keys, but stores them as plain text in its `api_keys`
  table. Since the API/crons share Postgres with Miniflux, they resolve a
  token directly from that table on first call via
  `api/niouzou/services/miniflux_bootstrap.py` (generating + INSERTing one
  if absent, with `ON CONFLICT DO UPDATE`). Idempotent across restarts.
- `docker-compose.test.yml` is a **separate file** (not a profile) providing a
  tmpfs Postgres on port `5433` for pytest. Kept out of the main stack so
  there's zero risk of pytest's `TRUNCATE` fixtures targeting real data.

**Acceptance criteria — all met**:
- `docker compose up` from a clean machine starts the full stack, no manual step
- Alembic migrations run automatically once (via `migrate`) before `api` accepts traffic
- App accessible at `http://localhost:3000`
- Miniflux admin account provisioned on first boot; API token minted on
  first call by the API itself
- `pytest` targets the test database, never the dev database

---

#### [x] E6-S3 — Railway config ✅
- `railway.toml` declares all services.
- API service runs `python -m niouzou.scripts.ensure_miniflux_db && alembic upgrade head`
  as its `preDeployCommand` — the first half creates a sibling `miniflux`
  database on the shared Postgres if missing (Miniflux can't share the API's
  default DB because both define a `users` table); the second half applies
  migrations. Both halves are idempotent.
- Cron services use Railway's `cronSchedule` (the scripts are one-shot, so no
  sleep loop is needed there — unlike the compose stack).
- `VITE_API_URL` wired to `https://${{ api.RAILWAY_PUBLIC_DOMAIN }}/api/v1` so
  Railway's Dockerfile build receives it as a build ARG.
- "Deploy on Railway" button in README.
- The Miniflux API token is auto-provisioned at runtime (same mechanism as
  the compose stack — see E6-S2).

---

#### [x] E6-S4 — Repository & licence ✅
- `LICENSE` file: GNU AGPL-3.0 (relicensed in E18).
- `README.md`: pitch + one-command self-hosting quickstart + Railway deploy
  button + env var reference + screenshots + known MVP limitations.
- `docs/` folder committed with all architecture documents.
- README documents the following known MVP limitations:
  - **Refresh tokens non-revocable**: JWTs are stateless, valid for 30 days, no blacklist. A logout or compromised token cannot be invalidated before expiry.
  - **Miniflux feed deduplication is global**: if two users add the same RSS URL, Miniflux deduplicates at the feed level — the second `POST /sources` may return an error or the existing feed. Articles from a shared feed are only ingested under the first user's source. Harmless in single-user setups.
  - **Relevance scores frozen at enrichment**: a user who registers after an article was enriched has no `relevance_score` for it and will never see it in their feed (unless a backfill is run — see Epic 5 open item).
  - **`RANDOM_SURFACE_RATE` + keyset pagination**: with `SCORE_THRESHOLD > 0`, the random branch is re-evaluated on every request, so pages may be unstable. With the default `SCORE_THRESHOLD = 0.0`, the feed is 100% deterministic.

---

## EPIC 7 — PWA Polish & Follow-up

**Goal**: Address known limitations and bugs surfaced during first real-world testing. None are blockers for continued use but should be resolved before the app is widely shared.

> These items were consciously deferred during Epic 4 to keep scope manageable.
> They are collected here so nothing is forgotten.

### Stories

#### [x] E7-S1 — Card readability: reduce background transparency

**Problem**: Article cards use a glass/translucent style that makes text unreadable when rendered over the animated blob background.

**Work**:

- Increase the card background opacity so text always has sufficient contrast against the blob background
- Adjust backdrop-blur and background color to find the right balance between the glass aesthetic and readability
- Verify legibility on both light and dark blob phases (the blobs animate through multiple color stops)

**Acceptance criteria**:

- Title, summary, source, and score badge are readable at a glance without squinting
- Cards still visually feel part of the design system (not a plain white box)

---

#### [x] E7-S2 — Like/dislike from article detail: return to feed

**Problem**: Tapping like or dislike while reading an article detail view submits feedback but leaves the user on the article — they have to manually press Back to continue swiping.

**Work**:

- In `ArticleDetail.tsx`, after a successful `POST /feedback` with action `like` or `dislike`, call `navigate(-1)` to return to the previous screen (the feed or the saved list)
- Save action (`save`/`unsave`) should NOT navigate back — the user may still want to read the article
- The back-navigation must happen after the API call confirms success (not optimistically) to avoid losing feedback on a network error

**Acceptance criteria**:

- Like or dislike from article detail navigates back to the feed immediately after the request succeeds
- Save/unsave from article detail keeps the user on the article
- If the feedback request fails, the user stays on the article and sees an error message

---

#### [x] E7-S3 — Missing article images: investigate and fix

**Problem**: Article cards and the article detail view show no image. The design expects an `og:image` URL on every article; the current data has it systematically empty or null.

**Investigation areas** (in order):

1. **Miniflux**: check whether the Miniflux entry payload (`GET /v1/entries`) includes an image URL field (check `enclosures`, `feed.icon`, and the entry's own fields). Miniflux does not always extract og:image — it depends on the feed type and Miniflux version.
2. **`cron_fetch`**: verify that `articles.og_image_url` is populated from the Miniflux entry. If Miniflux exposes the image under a non-obvious field, map it here.
3. **`cron_enrich`**: if Miniflux never provides og:image, `newspaper4k` (already used for content extraction) can extract it from the scraped page — add `og_image_url` extraction as a fallback step after content fetch.
4. **PWA**: confirm that `ArticleCard.tsx` and `ArticleDetail.tsx` actually render the image when the URL is non-null (rule out a display bug independent of the data).

**Work** (after investigation determines root cause):

- Fix the identified gap in the pipeline (Miniflux mapping, `cron_fetch`, or `cron_enrich`)
- If the fix is in `cron_enrich` (newspaper4k fallback), add it as an optional step that only fires when `og_image_url` is still null after the Miniflux import
- Add a one-off backfill script (or a cron run flag) to populate `og_image_url` for already-enriched articles that are missing it

**Acceptance criteria**:

- Newly enriched articles have a non-null `og_image_url` for at least 80% of articles from mainstream RSS feeds
- Cards and article detail display the image when the URL is present
- Articles with no extractable image fall back gracefully (placeholder or no image area — no broken img tag)

---

#### [x] E7-S4 — Keyword extraction: filter stop words

**Problem**: Keyword extraction (both TF-IDF and AI paths) returns common function words — articles, prepositions, conjunctions (e.g. "des", "les", "un", "et", "de", "la", "le") — that carry no signal and pollute the keyword weights list.

**Work**:

- Add a French + English stop-word list to `niouzou/scoring/` (a plain set of ~200 words is sufficient — no external library needed)
- Filter out stop words in `TFIDFScorer.extract_keywords()` before returning candidates
- Filter out stop words in `AIKeywordScorer.extract_keywords()` after parsing the LLM JSON
- Also filter single-character tokens and purely numeric tokens

**Acceptance criteria**:

- Running enrichment on a French-language article produces zero stop words in `article_keywords`
- Existing `article_keywords` rows containing stop words are not automatically cleaned (leave for a one-off migration if needed)

---

#### [x] E7-S5 — Max keywords per article

**Problem**: There is no upper bound on the number of keywords stored per article. TF-IDF and the LLM can both return many low-salience candidates, creating noise in the keyword weights list and slow queries.

**Work**:

- Add `MAX_KEYWORDS_PER_ARTICLE` env var (default: `6`)
- In `ScoringService.extract_and_store_keywords()`, after receiving candidates from the scorer, take only the top N by salience before writing to `article_keywords`
- The limit is applied at the persistence layer, not inside the scorers, so it works for both TF-IDF and AI paths

> **E8 hook**: `MAX_KEYWORDS_PER_ARTICLE` will be added to the admin-overridable keys in E8-S2/E8-S3, so the limit can be changed at runtime without a redeploy.

**Acceptance criteria**:

- After enrichment, no article has more than `MAX_KEYWORDS_PER_ARTICLE` rows in `article_keywords`
- Changing the env var to `10` keeps the top 10 keywords for newly enriched articles

---

#### [x] E7-S6 — Cold-start scoring: bypass threshold for new users

**Problem**: A new user has no `keyword_weights`. All article keywords resolve to weight 0 (neutral), pushing every relevance score to ~50% via the sigmoid. With a `SCORE_THRESHOLD` above 0.5 (e.g. 0.6), the feed is completely empty from day one — a broken first-run experience.

**Concept**: Treat the feed as threshold-free until the user has built up enough signal. The threshold should only gate articles once the scoring has enough data to be meaningful.

**Work**:

- Add `COLD_START_THRESHOLD` env var (default: `10` feedbacks)
- In `FeedService.get_feed()`, count `article_feedbacks` for the current user. If the count is below `COLD_START_THRESHOLD`, pass `min_score=0.0` regardless of `SCORE_THRESHOLD`
- When cold-start mode is active, include a `cold_start: true` flag in the `GET /feed` response metadata so the PWA can optionally show a "Keep swiping to personalise your feed" banner

**Acceptance criteria**:

- A brand-new user with `SCORE_THRESHOLD=0.8` sees all available articles
- After 10 feedbacks, the threshold applies normally
- Changing `COLD_START_THRESHOLD` via env var takes effect without a code change

---

#### [x] E7-S7 — Scoring method indicator

**Problem**: It is impossible to know whether an article's relevance score was computed by the AI scorer or TF-IDF — useful for debugging and user trust.

**Work**:

- Add a `scorer` column (`VARCHAR`, nullable) to `article_relevance_scores`: stores `"tfidf"` or `"ai_keyword"` at write time
- `ScoringService.score_article_for_user()` passes the active scorer name through to the insert
- Include `scorer` in the `ArticleRelevanceScore` schema and in the `FeedArticle` / `ArticleDetail` API response shapes
- PWA: display a subtle badge on the score pill (e.g. "AI" vs "TF-IDF") on both the feed card and the article detail view

**Acceptance criteria**:

- `GET /feed` response includes `scorer` on each article
- The scorer badge is visible but unobtrusive — does not compete with the score value itself

---

#### [x] E7-S8 — Feed empty state: lower score threshold on demand

**Problem**: When a user has swiped through all available articles, the Feed shows an empty state. Articles below `SCORE_THRESHOLD` are already in the DB (fetched and enriched) but filtered out. There is no way to access them without waiting for new content.

**Concept**: Rather than triggering a new RSS fetch, the empty state offers to widen the score filter — the user explicitly opts in to lower-quality articles, with the target score shown upfront.

**API changes**:

- Add an optional `min_score` query parameter to `GET /feed`: overrides `SCORE_THRESHOLD` for that request only
- `min_score` must be ≥ 0.0 and ≤ 1.0; if omitted, the server default applies as today
- The existing `RANDOM_SURFACE_RATE` and gravity logic still apply — only the floor changes

**PWA changes**:

- Empty state in `Feed.tsx` shows two elements:
  1. A message: "Vous avez tout lu !"
  2. One or two buttons offering a lower threshold, label explicitly showing the target score:
     - "Voir les articles avec score ≥ 0.2" (or whatever the stepped-down value is)
     - If already at a lowered threshold and still empty: "Voir tous les articles (score ≥ 0)"
- The stepped-down value is computed as `max(current_min_score - SCORE_STEP, 0)` where `SCORE_STEP = 0.1` (hardcoded in the PWA)
- Tapping a button reloads the feed with the new `min_score` passed as query param; the current floor is stored in local component state (resets to default on full page reload)
- The active floor is shown as a subtle pill/badge on the Feed screen ("Score ≥ 0.2") so the user knows they are in relaxed mode

---

#### [x] E7-S9 — `/me` endpoint + real Profile stats

**Problem**: The Profile screen computes stats (Saved / Keywords / Sources) from the first page of each list endpoint — not the real total. Email is stored from the login form, not from the server.

**Work**:

- Add `GET /me` endpoint returning `{ email, is_admin, saved_count, keyword_count, source_count }` (real DB `COUNT`s)
- Update `Profile.tsx` to use `/me` instead of the three parallel calls
- Store email from `/me` response (not from the login form input)

> **E8 hook**: `is_admin` is returned here so the PWA can conditionally show the "Administration" link (introduced in E8-S4).

---

#### [x] E7-S10 — Keywords displayed on cards and article detail

**Problem**: Keyword tags are specified in the design (E1-S2, E1-S3) and in the API response shape but are not rendered in the current PWA implementation. Benefits from E7-S4 (stop word filtering) having been applied first.

**Work**:

- Feed card (`ArticleCard.tsx`): render keyword tags below the summary, showing the top 3 keywords by salience (truncate with "+" if more)
- Article detail (`ArticleDetail.tsx`): render all keywords as a scrollable tag row
- Keyword tags are display-only on the card; on the detail view, tapping a tag navigates to `/keywords` with that term highlighted (nice-to-have, not a hard requirement)

**Acceptance criteria**:

- Keywords appear on cards without breaking the card layout on small screens
- Empty keyword list renders nothing (no empty tag row)

---

#### [x] E7-S11 — Saved screen: optimistic insert when saving from Feed

**Problem**: An article saved via swipe/button in the Feed does not appear in the Saved screen until pull-to-refresh. Articles unsaved from the detail view disappear immediately (via the `feedbacks` store overlay).

**Work**:

- Extend `feedbackStore` or add a `savedStore` that also holds the full `FeedArticle` object when `action === 'save'`
- `Saved.tsx` merges this session-saved list on top of the server response (same pattern as the existing unsave filter)

---

#### [x] E7-S12 — Infinite scroll on Saved & Keywords

**Problem**: `getSaved()` and `getKeywords()` only fetch the first page. Users with many saved articles or many keywords see a truncated list.

**Work**:

- Add infinite scroll / "load more" button to `Saved.tsx` (follow next_cursor from the API)
- Add infinite scroll / "load more" button to `Keywords.tsx` (follow next_cursor)

---

#### [x] E7-S13 — Keywords: lock indicator + de-override + reset all

**Problem**: When a user manually edits a keyword weight, the `PATCH /keywords/:term` response sets `manually_overridden = true` server-side (so `cron_refresh_weights` skips it). The PWA gives no visual feedback that the weight is pinned, and there is no way to undo the override or wipe the slate clean.

**API changes**:

- Extend `PATCH /keywords/:term` body to accept `{ weight?: float, manually_overridden?: bool }` — sending `{ "manually_overridden": false }` alone clears the pin without changing the weight value; sending `{ "weight": 0.8 }` still behaves as before (sets `manually_overridden = true`)
- Add `DELETE /keywords` endpoint: deletes **all** `keyword_weight` rows for the current user (hard delete, irreversible); returns `204 No Content`

**PWA changes**:

- Show a small lock icon on `KeywordWeight` rows where `manually_overridden = true`; the flag must be stored in the `overrides` map alongside `weight`
- Add an "unlock" icon button per locked row: calls `PATCH /keywords/:term { "manually_overridden": false }`, then updates the local state (icon disappears, weight stays until next cron run)
- Add a "Reset all keywords" button at the top of `Keywords.tsx`: opens a confirmation modal ("This will delete all your keyword weights. This cannot be undone."); on confirm calls `DELETE /keywords`, then clears local keyword state and refetches

---

#### [x] E7-S14 — Multi-user: same RSS feed subscribed by two users

**Problem**: Miniflux is a single shared instance with one set of admin credentials. If two Niouzou users add the same RSS URL:
1. The second `POST /sources` call fails with `bad_request` — `miniflux.create_feed()` returns a 422 because the feed already exists.
2. Even if it succeeded, `cron_fetch`'s `feed_id → source_id` mapping is not multi-valued: only one user's source would receive articles.

This is a non-issue for single-user self-hosting (the documented primary use case) but blocks any shared deployment.

**Work**:

- In `SourcesService._register_in_miniflux`: catch the 422 from Miniflux, retrieve the existing feed id via `GET /v1/feeds` filtered by URL, and return it instead of failing.
- In `cron_fetch._source_id_by_feed`: change the dict to `dict[int, list[str]]` (feed_id → list of source_ids) and insert articles for every matching source.

**Note**: The documented MVP limitation in E6-S4 ("Miniflux feed deduplication is global") should be removed from the README once this story is done.

---

#### [x] E7-S15 — Health screen + AI enrichment stats

**Problem**: When self-hosting, there is no way to know whether crons are running, how many articles are pending, or — critically — whether AI enrichment is working or silently falling back to TF-IDF after errors.

**Schema changes**:

- Add `enrichment_method` VARCHAR nullable to `articles`: set to `'ai'` or `'tfidf'` by `cron_enrich` after each article is processed
- Add `enrichment_error` TEXT nullable to `articles`: set to the error message when AI fails and fallback is triggered; `null` on success

**API changes**:

Add `GET /stats` (authenticated):

```json
{
  "articles": {
    "total": 1842,
    "pending_enrichment": 7,
    "last_fetched_at": "2026-05-27T14:03:00Z"
  },
  "sources": {
    "total": 12,
    "active": 12
  },
  "keywords": {
    "total": 94,
    "manually_overridden": 3
  },
  "enrichment": {
    "last_enriched_at": "2026-05-27T14:10:00Z",
    "total_ai": 1456,
    "total_tfidf_fallback": 42,
    "last_error": "JSONDecodeError: Expecting value: line 1 column 1",
    "last_error_at": "2026-05-20T13:45:00Z"
  }
}
```

All values derived from existing tables + new columns — no additional tables required:
- `last_fetched_at`: `MAX(created_at)` on `articles` filtered by the user's sources
- `last_enriched_at`: `MAX(enriched_at)` on `articles`
- `pending_enrichment`: `COUNT` where `enriched_at IS NULL`
- `total_ai` / `total_tfidf_fallback`: `COUNT` grouped by `enrichment_method`
- `last_error` / `last_error_at`: row with non-null `enrichment_error`, ordered by `enriched_at DESC`, limit 1

**`cron_enrich` changes**:

- On successful AI enrichment: set `enrichment_method = 'ai'`, `enrichment_error = null`
- On fallback to TF-IDF: set `enrichment_method = 'tfidf'`, `enrichment_error = str(exception)`

**PWA changes**:

- Add a "System" collapsible section at the bottom of `Profile.tsx`
- Display cron health: last fetch time, last enrich time, pending articles count
- Display AI stats: "X articles enriched with AI, Y with TF-IDF fallback"
- If `total_tfidf_fallback > 0`, show an amber warning with the last error message (truncated to 80 chars) and its timestamp
- Timestamps shown as relative ("3 minutes ago") with the absolute time on tap/hover
- If `last_fetched_at` is more than 2× `CRON_FETCH_INTERVAL` ago, show a warning ("Feed may be stalled")

---

#### [x] E7-S16 — Manual cron trigger

**Problem**: On a fresh install, the first cron tick can be up to 15–30 minutes away. There is no way to trigger the pipeline manually without SSH access.

**API changes**:

Add `POST /admin/refresh` (requires `require_admin` from E8-S1):
- Returns `202 Accepted` immediately with `{ "status": "started" }`
- Runs `cron_fetch` then `cron_enrich` sequentially as a FastAPI `BackgroundTasks` job
- Requires extracting the core logic of each cron into callable service functions (`FetchService.run()`, `EnrichService.run()`)
- Guard against concurrent runs: if a job is already in progress, return `202` without starting a second one (simple in-memory flag is sufficient for a single-process deployment)

> **Dependency**: requires E8-S1 (admin role) for the `require_admin` guard on `POST /admin/refresh`.

**PWA changes**:

- Add a "Run now" button in the System section of `Profile.tsx` (introduced in E7-S15), next to the cron status indicators
- On tap: call `POST /admin/refresh`, disable the button and show a spinner
- Re-enable the button and refresh `/stats` after 10s
- Disable the button for 60s after a successful trigger (debounce)

---

#### [x] E7-S17 — ~~Feedback fire-and-forget retry~~ *(dropped)*

> Deferred indefinitely. Losing a single feedback on a brief blip is acceptable for a self-hosted single-user app. A proper offline queue is out of scope.

---

#### ~~E7-S18 — Keyword deduplication: merge similar keywords with existing ones~~

> Migrated to **E10-S1** (EPIC 10 — Scaling). See EPIC 10 for full spec.

---

#### [x] E7-S19 — Pull-to-refresh on background drag

**Problem**: On mobile, there is no native gesture to manually refresh the current screen. Users have to navigate away and back, or wait for the next automatic fetch. A swipe-up gesture on the background blob (not on a card or scrollable list) is the natural mobile pattern.

**Goal**: Add a pull-to-refresh gesture on the `BlobBackground` layer, available on every screen. Pulling from bottom to top triggers a soft refresh of the current screen's data.

**Behaviour**:

- The gesture is detected on the `BlobBackground` component (the decorative backdrop), not on scrollable content areas or swipeable cards — those must keep their existing touch handlers unaffected.
- Direction: drag from bottom toward top (upward swipe, min ~80 px travel) triggers the refresh.
- Visual feedback: while pulling, the app logo appears centered on screen and rotates (or pulses) in sync with the drag progress; once released, it spins continuously until the refresh completes, then fades out. No separate spinner or toast needed.
- What "refresh" means per screen:
  - **Feed** (`/`) — re-fetch `GET /feed` (discard current article stack, reload from the top)
  - **Saved** (`/saved`) — re-fetch `GET /saved` from the first page
  - **Keywords** (`/keywords`) — re-fetch `GET /keywords`
  - **History** (`/history`) — re-fetch `GET /history` from the first page
  - **Profile** (`/profile`) — re-fetch `GET /me`
  - Other screens (article detail, admin…) — no-op or navigate back

**Implementation notes**:

- Implement a `usePullToRefresh(onRefresh: () => void)` hook that listens to `touchstart` / `touchmove` / `touchend` events on a given ref and fires `onRefresh` when the upward threshold is met.
- `BlobBackground` receives an optional `onRefresh` prop; screens pass their own refresh callback.
- Guard against accidental triggers: require the touch to start in the bottom third of the viewport and travel upward by at least 80 px before releasing.
- Do not interfere with the card swipe gesture on the Feed screen (the swipe is horizontal; this gesture is vertical and starts from the background layer below the card stack).

**Acceptance criteria**:

- Dragging upward on the background blob from the bottom third of the screen triggers a visible loading indicator and re-fetches data on Feed, Saved, Keywords, History, and Profile.
- The gesture does not fire when the drag starts on a card, a list item, or a scrollable area.
- The horizontal swipe on Feed cards is unaffected.
- No duplicate requests: if a refresh is already in flight, a second gesture is ignored until the first completes.

---

#### [x] E7-S20 — Saved screen: scroll & text overflow

**Problem**: The Saved articles screen is missing proper scroll behaviour and long titles / sources overflow without being truncated, breaking the layout on mobile.

**Changes**:

- Ensure the list container is scrollable (overflow-y: auto or infinite scroll already in place via E7-S12 — verify it works end-to-end on real content).
- Add `truncate` (single-line ellipsis) or `line-clamp-2` (two-line cap) on article titles in the Saved list rows, consistent with the Feed card style.
- Add `truncate` on source names.
- Tooltip (`title` attribute) on truncated text so the full string is readable on long-press / hover.

**Acceptance criteria**:

- A very long title never overflows its row container.
- The list scrolls smoothly to the bottom on a full saved list.
- Truncated text is readable in full via the native tooltip.

---

#### [x] E7-S21 — Premium articles: surface paywall limitations clearly

**Problem**: When Miniflux fetches a paywalled article, the stored content is only the teaser visible before login. Nothing in the UI signals this to the user, so they tap "Read article" expecting full content and land on a paywall.

**Changes**:

- Detect premium/partial content: an article is considered partial when its `content` length is significantly shorter than its `summary_short` would suggest, or when a flag is returned by Miniflux (investigate available fields — `reading_time`, content length heuristic, or a dedicated field).
- On the **article detail view**: show a banner or badge ("Contenu partiel — article premium") above the summary.
- On the **"Read article" button**: change the label to something like "Voir sur le site (contenu limité)" and add a lock icon to make it clear the full article is behind a paywall.
- On **Feed cards**: add a small lock icon badge on the thumbnail when the article is detected as premium.

**Acceptance criteria**:

- Premium articles are visually distinct from free articles on the card and in the detail view.
- The CTA button wording sets the right expectation before the user taps it.
- Non-premium articles are unaffected.

---

#### [x] E7-S22 — Premium articles: exploration of credential-based full-content fetching

**Outcome**: Credential injection is not viable against WAF-protected sites (Le Monde / Akamai returns 402 even with valid session cookies + matching UA — only a headless browser would bypass it, which is out of scope). For client-side paywalls where the full HTML is served to anyone, enabling Miniflux's `crawler: true` per-feed is enough — Rugbyrama feed added on this basis.

---

#### [x] E7-S23 — Article detail: back button returns to same feed position

**Problem**: Tapping the back button from the article detail view triggers a "next article" action instead of restoring the feed at the article that was being viewed. The user loses their place.

**Root cause to investigate**: The Feed state (current article index / stack) is likely reset on navigation, causing the feed to advance one position when the detail view unmounts or the back event is handled.

**Expected behaviour**:

- Tapping back from article detail returns to the Feed (or Saved / History, depending on the entry point) with the same article still shown — no advance, no scroll jump.
- The article stack position is preserved across the detail route.

**Implementation notes**:

- Preserve the current article in Zustand (or React Router state) when navigating to `/articles/:id`.
- On back navigation, restore that state rather than calling `nextArticle()`.
- Cover the case where the user arrived from Saved or History — back should return to the correct list at the correct scroll position.

**Acceptance criteria**:

- Open an article from the Feed → tap back → the same article is displayed in the Feed (not the next one).
- Open an article from Saved → tap back → Saved list is restored at the same scroll position.
- No regression on the normal swipe-to-next flow.

---

#### [x] E7-S24 — Article detail: icon colours consistent with Feed

**Problem**: The action icons on the article detail view (like, dislike, save, share…) use different colours than their counterparts on the Feed home screen, creating visual inconsistency.

**Changes**:

- Audit all icon colours in `ArticleDetail.tsx` (or equivalent) against the Feed card action icons.
- Align them to the design tokens defined in `docs/DESIGN_SYSTEM.md` — do not hardcode new values.
- Ensure hover / active states also match.

**Acceptance criteria**:

- Like icon: same colour on Feed card and article detail.
- Dislike icon: same colour on Feed card and article detail.
- Save icon: same colour on Feed card and article detail.
- No new colour values introduced outside `DESIGN_SYSTEM.md`.

---

#### [x] E7-S25 — CI: automated unit test pipeline

**Goal**: Run the unit test suite automatically on every push and pull request so regressions are caught before merge.

**Scope**:

- API (Python / pytest) — existing and future unit tests under `api/`
- PWA (TypeScript / Vitest or Jest) — if a test suite exists or is added

**Implementation**:

- Add a GitHub Actions workflow file at `.github/workflows/ci.yml`
- Triggered on: `push` to `main`, and `pull_request` targeting `main`
- Jobs:

  **`test-api`**:
  - Runs on `ubuntu-latest`
  - Sets up Python 3.13
  - Installs dependencies (`pip install -e ".[dev]"` or `pip install -r requirements-dev.txt`)
  - Spins up a PostgreSQL service container (same major version as production) for tests that need a real DB
  - Sets the required env vars (`DATABASE_URL` pointing to the service container, `JWT_SECRET`, `MINIFLUX_URL` as a dummy value)
  - Runs `pytest api/ -q --tb=short`

  **`test-pwa`** *(conditional — only if a test script exists in `pwa/package.json`)*:
  - Runs on `ubuntu-latest`
  - Sets up Node.js (match `.nvmrc` or `engines` field in `package.json`)
  - Runs `npm ci && npm test -- --run` (non-interactive, no watch mode)

- Both jobs must pass for the workflow to be green; either job failing blocks the PR.
- Secrets: `JWT_SECRET` and any other sensitive values are stored as GitHub Actions secrets, not hardcoded.

**Acceptance criteria**:

- Pushing to `main` or opening a PR triggers the workflow automatically.
- A failing test causes the workflow to exit non-zero and the check is marked red on the PR.
- The workflow completes in under 3 minutes on a cold runner for the current test suite size.
- No secrets appear in workflow logs.

---

#### [x] E7-S26 — Full-content fetch toggle for sources (Miniflux crawler)

**Problem**: Adding a source from the PWA creates the Miniflux feed with default settings (`crawler: false`). For publishers whose RSS exposes only a teaser (Rugbyrama and similar), articles are ingested as ~200-char snippets instead of full content. E7-S22 confirmed that enabling Miniflux's `crawler: true` per-feed retrieves the full article HTML for these sources, but the option is reachable today only via the Miniflux admin UI.

**Multi-user caveat**: A Miniflux feed is shared across all Niouzou users subscribed to the same URL (`sources.miniflux_feed_id` is not unique per user — see `api/niouzou/models/source.py`). The `crawler` flag lives on a shared resource, so any toggle by one user is visible to every other subscriber. Strategy: **last-write-wins, with a clear UI warning**. No per-user override (would require duplicating feeds in Miniflux, which it refuses).

**Changes**:

*API*:

- Extend `MinifluxClient.create_feed()` (`api/niouzou/services/miniflux_client.py`) with an optional `crawler: bool = False` passed through to `POST /v1/feeds`.
- Add `MinifluxClient.update_feed(feed_id, *, crawler: bool)` wrapping `PUT /v1/feeds/{id}`.
- Add `fetch_full_content: bool = False` to the `POST /sources` request body, plumbed through `SourcesService` into `create_feed(crawler=…)`.
- Add `PATCH /sources/{id}` accepting `{ "fetch_full_content": bool }`, which calls `update_feed`. The Niouzou-side `Source` row is unchanged; the state lives entirely on the Miniflux feed.
- Surface `fetch_full_content` (read from Miniflux's `crawler` field) in `GET /sources` so the PWA can render the current state.

*PWA — Ancien design (E7-S26 original)* :

Supprimé et remplacé par la version E11-S3bis ci-dessous. L'option utilisateur d'activer/désactiver la récupération du contenu complet a été retirée ; le comportement par défaut est désormais toujours activé pour les nouvelles sources.

*PWA — Nouveau design (E11-S3bis)* :

- "Add a source" form: suppression complète du checkbox **"Récupérer l'article complet"**. Le formulaire ne contient que le champ URL et le bouton Add.
- Nouvelles sources sont créées avec `fetch_full_content: true` par défaut.
- Source detail or list screen: suppression du toggle `FullContentToggle`. Les utilisateurs ne peuvent plus modifier le paramètre `fetch_full_content` via l'UI.
- Comportement : les sources créées avant cette modification gardent leur valeur `fetch_full_content` existante (pas de backfill) ; seules les **nouvelles** sources utilisent `true` par défaut.
- Colonne de DB non supprimée — elle reste available si une future feature permet à l'admin de l'ajuster pour toutes les sources d'un feed partagé.

**Acceptance criteria**:

- Adding a source with the checkbox ticked → Miniflux feed has `crawler: true`; next fetch produces articles with content length in the thousands (verified on a known teaser-only source).
- Adding a source with the checkbox unticked → `crawler: false` (current behaviour, no regression).
- Toggling on an existing source updates Miniflux in place and the next fetch reflects the change — no need to recreate the source.
- The shared-state warning is visible before the user toggles.
- No regression on existing sources where the RSS already contains full content.

**Out of scope**:

- Per-user crawler isolation (impossible without duplicating Miniflux feeds).
- Exposing other Miniflux per-feed options (`user_agent`, `cookie`, `scraper_rules`) — to be reopened if a concrete need appears.

---

#### [x] E7-S27 — System card: spacing fix + metric clarity

**Problem**: The System card in the Profile tab has two presentation issues:

1. **Spacing inconsistency**: The System card sits in a separate `<div>` with `marginTop: 24` outside the `flex flex-col gap-2` container that holds "Manage sources" and "Sign out". This makes the gap above System visually larger than between the other cards.

2. **Confusing metrics in the expanded panel**:
   - `1456 with AI · 384 with TF-IDF` — cumulative all-time counters; the user has no idea whether these refer to the last run or all articles ever processed.
   - `Last error` — no context about which job it belongs to, and only shown when `hasFallback && last_error`, so an AI error that happened without a TF-IDF fallback is silently hidden.
   - No "next run" information — the user can't tell when the next automatic fetch will happen.
   - "Pending enrichment" label — "pending" is internal jargon; the user doesn't know what it means.

**Changes (PWA only — no API changes)**:

- Move the System card `<button>` + expanded `<SystemPanel>` inside the same `flex flex-col gap-2` container as "Manage sources" and "Sign out". Remove the outer `<div>` with `marginTop: 24`.

- Replace the `total_ai / total_tfidf` counts line with a single **AI status** indicator:
  - `AI · Working` (green dot) — if `last_error` is null, or `last_error_at < last_enriched_at` (last run succeeded)
  - `AI · Last run failed` (amber dot) — if `last_error_at >= last_enriched_at` (last run errored)
  - `AI · Off (TF-IDF)` (neutral) — if `total_ai === 0` and `total_tfidf_fallback === 0`

- Add a **"Next fetch"** row below "Last fetch", computed client-side as `last_fetched_at + CRON_FETCH_INTERVAL_MS`. Show `in ~X min` when in the future, `soon` when overdue. This is an estimate — it can drift if a scheduled slot was skipped (e.g. a manual run was in progress); in that case the display stays on `soon` for up to one extra interval, which is acceptable.

- Rename "Pending enrichment" → **"Articles pending"**.

- Show the enrichment error whenever `last_error` is not null (remove the `hasFallback` gate). Use label **"Enrichment error"** instead of "Last error" so the user understands which job produced the error.

**Acceptance criteria**:

- The gap between "Sign out" and "System" matches the gap between "Manage sources" and "Sign out".
- The expanded System panel shows: Last fetch / Next fetch / Last enrichment / Articles pending / AI status / (error if any) / Run now button.
- "Next fetch" shows a countdown in whole minutes; when overdue it shows "soon".
- The AI status indicator is correct for all three states (working / last run failed / off).
- The enrichment error is shown whenever `last_error` is non-null, regardless of whether a TF-IDF fallback occurred.
- No regression on the "Run now" button behaviour.

---

#### [x] E7-S29 — Scroll cassé sur Sources, Saved et Keywords

**Problème** : Le défilement ne fonctionne pas sur trois écrans — Manage Sources (`/sources`), Saved (`/saved`) et Keywords (`/keywords`). L'utilisateur ne peut pas atteindre les éléments en bas de liste si la liste dépasse la hauteur du viewport.

**Investigation** : Vérifier pour chaque écran que le conteneur de liste a `overflow-y: auto` (ou `scroll`) **et** une hauteur contrainte (soit via `flex-1 min-h-0` dans un parent flex column, soit via `h-full`). Sans `min-h-0`, un enfant flex peut dépasser sans déclencher le scroll. Vérifier aussi que `BlobBackground` ou un conteneur parent ne bloque pas le scroll via `overflow: hidden`.

**Changements** :

- `Sources.tsx` : s'assurer que la liste des sources est dans un conteneur scrollable qui ne dépasse pas la hauteur disponible.
- `Saved.tsx` : vérifier la régression depuis E7-S20 — l'infinite scroll était censé fonctionner ; s'assurer que le conteneur de liste a bien `min-h-0` dans sa chaîne flex parente.
- `Keywords.tsx` : même vérification et correction.

**Acceptance criteria** :

- Sur chaque écran, si la liste dépasse le viewport, l'utilisateur peut défiler jusqu'au dernier élément.
- Le contenu ne déborde pas par-dessus la `BottomNav`.
- Aucune régression sur l'infinite scroll de Saved et Keywords (E7-S12).

---

## EPIC 8 — Admin Panel

**Goal**: Introduce an admin role. Admin users can view and update runtime configuration (LLM model, API keys) from within the app — no SSH or env-var editing required after initial setup.

> Depends on EPIC 3 (auth + DB) and EPIC 4 (PWA).

### Stories

#### [x] E8-S1 — Admin role

**API changes**:

- Add `is_admin` boolean column (default `false`, not null) to the `users` table — Alembic migration required
- The first user registered on a fresh instance is automatically promoted to admin (`is_admin = true`) if no admin exists yet
- Add a reusable FastAPI dependency `require_admin` that verifies `current_user.is_admin`; returns `403 Forbidden` otherwise
- Apply `require_admin` to all `/admin/*` routes

**Acceptance criteria**:

- A non-admin user calling any `/admin/*` endpoint receives `403`
- First registered user has `is_admin = true`; subsequent users have `is_admin = false`
- Alembic migration runs cleanly on an existing DB

**Docs to update**: add `is_admin BOOLEAN NOT NULL DEFAULT FALSE` to the `users` table definition in `docs/DATA_MODEL.md`.

---

#### [x] E8-S2 — App config persistence layer

**Problem**: Settings like `OPENROUTER_MODEL` and API keys are currently env-var-only. Changing them requires a redeploy or container restart.

**Work**:

- Add an `app_settings` table: `key VARCHAR PK`, `value TEXT`, `updated_at TIMESTAMP`
- Add `SettingsService` with `get(key)` and `set(key, value)` methods
- At startup, `config.py` continues to read from env vars. At runtime, `SettingsService.get(key)` checks `app_settings` first and falls back to the env var — DB overrides env (allows runtime changes without restart)
- Supported overridable keys: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `MAX_KEYWORDS_PER_ARTICLE`, `CRON_FETCH_INTERVAL`, `CRON_REFRESH_WEIGHTS_HOUR`
- When reading sensitive keys (`OPENROUTER_API_KEY`) for display, mask the value: show only `sk-...` prefix + last 4 chars (e.g. `sk-...a3f9`); return `null` if unset. Non-sensitive keys (`OPENROUTER_MODEL`, `MAX_KEYWORDS_PER_ARTICLE`, `CRON_FETCH_INTERVAL`, `CRON_REFRESH_WEIGHTS_HOUR`) are returned as-is.
- Exception: `CRON_FETCH_INTERVAL` and `CRON_REFRESH_WEIGHTS_HOUR` are read by the `refresh-worker` at startup only — changes to these two keys take effect on the next worker restart (cannot be applied live without rescheduling APScheduler jobs).

**Acceptance criteria**:

- After `SettingsService.set("OPENROUTER_MODEL", "gpt-4o")`, the next enrichment cron uses the new model without a restart
- Env vars remain the source of truth if no DB override exists

**Docs to update**: add the `app_settings` table (`key VARCHAR PK`, `value TEXT`, `updated_at TIMESTAMP`) to `docs/DATA_MODEL.md`.

---

#### [x] E8-S3 — Admin config endpoints

Add the following endpoints (all require `require_admin`):

- `GET /admin/config` — returns current effective values for all overridable keys:
  ```json
  {
    "openrouter_model": "anthropic/claude-3.5-sonnet",
    "openrouter_api_key": "sk-...a3f9",
    "max_keywords_per_article": 6,
    "cron_fetch_interval": 15,
    "cron_refresh_weights_hour": 3
  }
  ```
  API keys are always masked. Non-sensitive keys returned as-is.

- `PATCH /admin/config` — partial update; body may contain any subset of the overridable keys:
  ```json
  { "openrouter_model": "openai/gpt-4o" }
  ```
  Returns the updated config (masked). Sending an empty string for an API key deletes the DB override (falls back to env var). Changes to `cron_fetch_interval` and `cron_refresh_weights_hour` are persisted but take effect on next worker restart.

- **`GET /stats` extension**: add `cron_fetch_interval_minutes` (integer) to the top-level of the `GET /stats` response so the PWA can compute the "Next fetch" countdown (E7-S27) without hardcoding. The value is read from `SettingsService` (DB override then env var fallback).
  ```json
  { "cron_fetch_interval_minutes": 15, "articles": { … }, … }
  ```

- `GET /admin/models` — proxies the OpenRouter models catalogue, applies server-side filters, and returns a curated list ready for the PWA selector:
  - Calls `GET https://openrouter.ai/api/v1/models` with the stored OpenRouter API key.
  - **Filters applied**:
    - Input price ≤ $0.10 / 1 M tokens
    - Output price ≤ $0.40 / 1 M tokens
    - Modality is `text→text` only (exclude multimodal-only, image-generation, embedding, etc.)
    - Architecture suited for instruction-following / summarisation: exclude base/completion-only models (no instruct or chat variant). In practice: keep models whose `id` or `description` indicates chat/instruct capability, or whose `context_length` ≥ 8 000 (proxy for capable models).
  - Response shape per item:
    ```json
    {
      "id": "mistralai/mistral-7b-instruct",
      "name": "Mistral 7B Instruct",
      "input_price_per_m": 0.07,
      "output_price_per_m": 0.07,
      "context_length": 32768
    }
    ```
  - Results are sorted by `input_price_per_m ASC` then `name ASC`.
  - If the OpenRouter API key is not configured, returns `424 Failed Dependency` with a descriptive message.
  - Results are cached in-process for 1 hour to avoid hammering the OpenRouter catalogue on every admin page open.

**Acceptance criteria**:

- `GET /admin/config` never returns a plaintext API key
- `PATCH /admin/config` with a new model value is reflected immediately in subsequent calls to `GET /admin/config`
- `GET /admin/models` returns only models within the price caps, text-to-text only, sorted by input price
- `GET /admin/models` with no API key configured returns `424`
- Non-admin calling any of these endpoints receives `403`

**Docs to update**: add `GET /admin/config`, `PATCH /admin/config`, and `GET /admin/models` endpoint specs to `docs/API_SPEC.md`. Also extend the `GET /stats` response shape with `cron_fetch_interval_minutes`.

---

#### [x] E8-S4 — PWA admin screen

**New route**: `/admin` — only reachable if `current_user.is_admin`.

**Profile screen changes**:

- Show an "Administration" menu item in `Profile.tsx` (below "Manage sources") only when the current user is admin — determined via the `is_admin` field returned by `GET /me` (added in E7-S9)
- Tapping "Administration" navigates to `/admin`

**Admin screen (`Admin.tsx`)**:

- Protected: redirect to `/` if user is not admin (client-side guard in addition to API-level guard)
- Header: "Administration" with a back button
- Four config rows, each with a label, current value, and an edit button:
  - **OpenRouter API key** — masked display; edit opens an inline input (password type)
  - **OpenRouter model** — shows current model name; edit opens a searchable `<select>` (or dropdown list) populated by `GET /admin/models`. Each option displays `{name} — {input_price}$ in / {output_price}$ out per M tokens`. A loading state is shown while the model list is fetching; if the call fails (no API key, network error) the field falls back to a plain text input so the admin can still type a model ID manually.
  - **Fetch interval** — integer input (minutes); helper text "How often the pipeline fetches new articles. Takes effect on next worker restart."
  - **Weight refresh hour** — integer input (0–23, UTC); helper text "UTC hour for the daily keyword-weight recompute. Takes effect on next worker restart."
- Each row has a "Save" button that calls `PATCH /admin/config` with only that key; shows a success checkmark or error inline
- Unsaved changes are discarded on navigation (no dirty-state warning needed)

**Acceptance criteria**:

- Non-admin users do not see the "Administration" link on Profile and are redirected away from `/admin`
- The model dropdown is populated from `GET /admin/models`; each option shows name + input/output price
- Selecting a model from the dropdown and saving sends its `id` to `PATCH /admin/config`; the displayed value updates without a full page reload
- If `GET /admin/models` fails, the field degrades to a plain text input (no broken UI)
- API key fields never show the plaintext value fetched from the server (masked on display, only the new value typed by the user is sent)
- Fetch interval and weight refresh hour fields display the current effective value (DB override or env var default)

**Docs to update**: add the `GET /admin/users` and `PATCH /admin/users/{user_id}/password` endpoint specs to `docs/API_SPEC.md` (done here alongside E8-S5 which shares the same file section).

---

#### [x] E8-S5 — User management (listing + password reset)

**Goal**: Admins can see all registered users and reset any user's password from the admin screen — without SSH or DB access.

**API changes**:

- `GET /admin/users` — returns the list of all users:
  ```json
  [
    { "id": "uuid", "email": "alice@example.com", "is_admin": true, "created_at": "2024-01-01T00:00:00Z" }
  ]
  ```
  Sorted by `created_at ASC`. No pagination needed (user counts on self-hosted instances are small).

- `PATCH /admin/users/{user_id}/password` — sets a new password for any user:
  ```json
  { "new_password": "hunter2" }
  ```
  Returns `204 No Content`. Enforces the same password validation rules as registration (min length). An admin can reset their own password too. The target user's existing sessions are **not** invalidated (keep it simple — no token revocation needed here).

**PWA changes** (extend `Admin.tsx` from E8-S4):

- Add a "Users" section below the config rows, with a collapsible list of all users
- Each row shows: email, "Admin" badge if `is_admin`, creation date
- Each row has a "Reset password" button that opens an inline input (type `password`) with a "Save" button
- Saving calls `PATCH /admin/users/{user_id}/password`; shows a success checkmark or inline error
- The admin's own row is visually distinguished (e.g. "You" label) but is still editable

**Acceptance criteria**:

- `GET /admin/users` returns all users; non-admin receives `403`
- `PATCH /admin/users/{user_id}/password` with a password shorter than the minimum returns `422`
- `PATCH /admin/users/{non_existent_id}/password` returns `404`
- Non-admin users do not see the Users section (client-side guard + API-level `403`)
- Password input is never echoed in plaintext in the UI after save

**Docs to update**: add `GET /admin/users` and `PATCH /admin/users/{user_id}/password` to `docs/API_SPEC.md`.

---

#### [x] E8-S6 — Cron consolidation: move scheduled jobs into the Refresh Worker

**Problem**: As of E7-S16, there are **6 Railway services** for the backend: `api`, `pwa`, `refresh-worker`, `cron-fetch`, `cron-enrich`, `cron-refresh-weights`. The three cron services execute the pipeline scripts one-shot directly against the DB, completely bypassing the `refresh-worker`. This creates two parallel execution paths with no coordination:
- Railway crons call the DB directly (no lock, no awareness of each other)
- `POST /admin/refresh` calls the `refresh-worker`, which owns a single `asyncio.Lock`

A concurrent Railway cron run and a manual "Run now" trigger can execute `cron_fetch` or `cron_enrich` simultaneously, with no mutual exclusion. Additionally `cron_fetch` (every 15 min) and `cron_enrich` (every 30 min) are not chained — articles fetched at 14:15 may wait until 14:30 to be enriched.

**Goal**: Eliminate the three Railway cron services. Move all scheduled execution into the `refresh-worker` using APScheduler. The worker becomes the single point of truth for scheduled and on-demand pipeline execution.

**API changes**: none — `POST /admin/refresh` continues to proxy to `refresh-worker.railway.internal/run`.

**Worker changes** (`api/niouzou/workers/refresh_worker.py`):
- Add `apscheduler[asyncio]` dependency (or `APScheduler>=3.10`)
- Extract a shared `_guarded_run()` coroutine that both the scheduler and the `POST /run` endpoint call — this is the critical point for correct mutual exclusion:
  ```python
  async def _guarded_run() -> None:
      if _lock.locked():
          logger.info("refresh_worker: scheduled run skipped — already running")
          return
      async with _lock:
          await _run_pipeline()
  ```
  The existing `POST /run` handler is updated to `asyncio.create_task(_guarded_run())` instead of its current inline `_guarded()` closure. If both paths called `_run_pipeline()` directly without this wrapper, the lock would never be acquired by the scheduler and the two paths could race.
- On FastAPI `startup` event, read `CRON_FETCH_INTERVAL` (integer minutes) and `CRON_REFRESH_WEIGHTS_HOUR` (integer UTC hour) from `SettingsService` (DB override then env var fallback), then create an `AsyncIOScheduler` and register:
  - `_guarded_run` via `CronTrigger(minute=f"*/{cron_fetch_interval}")` (wall-clock aligned) — `misfire_grace_time=300` so a restart close to the trigger doesn't skip the job. Use `CronTrigger` rather than `IntervalTrigger` so the fire times are predictable and `last_fetched_at + N min` (computed in E7-S27 via `GET /stats`) remains a valid client-side estimate.
  - `cron_refresh_weights.run()` directly (no pipeline lock needed — it's independent) daily at `cron_refresh_weights_hour:00 UTC` — `misfire_grace_time=3600`
- The scheduler reads these values once at startup. Changes persisted via `PATCH /admin/config` (E8-S3) take effect on the next worker restart.

**Concurrency behaviour**:
- Scheduled run in progress → manual `POST /run` → `_lock.locked()` is True → returns `{"status": "already_running"}` immediately. PWA shows the button grayed as "Triggered". No double run.
- Manual run in progress → scheduler fires → `_lock.locked()` is True → `_guarded_run()` logs "skipped" server-side and returns. Next scheduled slot is in ≤15 min. No user-visible message needed (user triggered the run themselves).
- First-come, first-served: no priority between manual and scheduled. Whoever acquires `_lock` first runs; the other yields.
- Log scheduler start, job fire, and job completion at INFO level.

**Railway cleanup**:
- Delete `api/cron-fetch.railway.toml`, `api/cron-enrich.railway.toml`, `api/cron-refresh-weights.railway.toml`
- Remove the three cron services from the Railway dashboard **before** deploying the updated worker, to avoid a double-run window.

**Docker Compose changes** (`docker-compose.yml`):
- Replace the three cron services (currently wrapping one-shot scripts in a restart loop) with a single `worker` service using the same image as `api`, start command `uvicorn niouzou.workers.refresh_worker:app --host 0.0.0.0 --port 8001`, `restart: unless-stopped`. No `depends_on` change needed (worker already depends on `db` and `miniflux` indirectly via the scripts).

**Environment variable additions**:
- `CRON_FETCH_INTERVAL` (already documented, default `15`) — now also overridable via `app_settings` (E8-S2); used by the scheduler at startup
- `CRON_ENRICH_AFTER_FETCH` — not needed; enrich is always chained after fetch in `_run_pipeline()`
- `CRON_REFRESH_WEIGHTS_HOUR` — new, default `3` — UTC hour for the daily weight refresh; also overridable via `app_settings` (E8-S2)

**Docs to update**: add `CRON_REFRESH_WEIGHTS_HOUR` to the environment variables table in `docs/ARCHITECTURE.md`. Update the "Known limitation" note in the Railway section to reference E8-S6 instead of E9-S1.

**Acceptance criteria**:
- After deployment, the Railway project shows 3 services: `api`, `pwa`, `refresh-worker`
- The worker logs show scheduled job fires at approximately every 15 min and once at 03:00 UTC
- `POST /admin/refresh` continues to work: returns `{"status": "started"}` or `{"status": "already_running"}` correctly
- A manual `POST /admin/refresh` during a running scheduled job returns `already_running` (the lock is shared)
- Docker Compose: `docker-compose up` starts the stack with a single `worker` service; no separate cron containers
- No regression on `cron_refresh_weights` — keyword weights are recomputed daily

**Out of scope**:
- Persistent job state (APScheduler memory scheduler is sufficient; a missed daily job on restart is acceptable)
- Dynamic rescheduling without restart (interval changes require a worker restart — acceptable)
- Per-user cron isolation

---

## EPIC 9 — Refonte UX TikTok-like

**Objectif** : Remplacer le feed à mini-cartes par un feed fullscreen scroll-snap vertical (style TikTok), séparer le système de feedback (save / like / dislike / read deviennent des états indépendants), refondre le scoring en conséquence, et introduire un onglet Explore (file d'actu : history + new).

> Dépend de EPIC 3, EPIC 4, EPIC 5.

**Ordre de livraison** : `S1 → (S2, S4 en parallèle) → S3`. S1 est bloquant pour tout le reste (nouveaux champs dans les payloads d'article + nouveau shape `POST /feedback`).

---

### Nouveau modèle de feedback

`article_feedbacks` est restructuré pour séparer la réaction, la sauvegarde et la lecture :

```sql
-- Nouvelles colonnes (migration, ancienne `action` supprimée)
reaction            VARCHAR(10) NOT NULL DEFAULT 'none'
                    CHECK (reaction IN ('like', 'dislike', 'none')),
is_saved            BOOLEAN NOT NULL DEFAULT false,
read_full_article   BOOLEAN NOT NULL DEFAULT false
```

Un article peut simultanément avoir `reaction = 'like'`, `is_saved = true` et `read_full_article = true` — les trois dimensions sont indépendantes.

**Sémantique des transitions** :

| Champ               | Transitions autorisées | Justification |
|---------------------|------------------------|---------------|
| `reaction`          | bidirectionnelle (like ⇄ dislike ⇄ none) | L'utilisateur peut changer d'avis (re-tap = retour à `none`) |
| `is_saved`          | bidirectionnelle (un-save autorisé) | Geste bookmark classique |
| `read_full_article` | **monotone** (`false → true` uniquement) | Un read est un événement, pas un état réversible. Le backend ignore silencieusement un payload `{ read_full_article: false }`. |

**Migration des données existantes** :
- `action = 'like'`    → `reaction = 'like'`
- `action = 'dislike'` → `reaction = 'dislike'`
- `action = 'save'`    → `is_saved = true`, `reaction = 'none'`
- `action = 'skip'`    → ligne supprimée (skip n'était jamais consommé en scoring)

**Nouveau modèle de scoring** (contribution d'un article au poids de ses keywords) :

| Signal                       | Contribution |
|------------------------------|--------------|
| `reaction = 'like'`          | +1.0  |
| `reaction = 'dislike'`       | −1.0  |
| `is_saved = true`            | +0.5  |
| `read_full_article = true`   | +0.5  |
| Tous les champs neutres      | 0     |

Les signaux s'accumulent par article : un article liked + saved + read = +2.0 pour ses keywords. Un article disliked + saved (cas tordu mais légal — l'utilisateur veut le garder pour référence) = −0.5.

**Expression SQL canonique** (à reproduire dans `services/weights.py`) :

```sql
salience * (
  CASE WHEN fb.reaction = 'like'    THEN  1.0
       WHEN fb.reaction = 'dislike' THEN -1.0
       ELSE 0 END
  + CASE WHEN fb.is_saved          THEN 0.5 ELSE 0 END
  + CASE WHEN fb.read_full_article THEN 0.5 ELSE 0 END
)
```

---

### Stories

#### [x] E9-S1 — Data model & scoring refactor *(backend)*

**Migration Alembic** :

- Ajouter `reaction`, `is_saved`, `read_full_article` à `article_feedbacks` (defaults ci-dessus, NOT NULL).
- Backfill via un seul `UPDATE` selon la table de migration ci-dessus.
- `DELETE FROM article_feedbacks WHERE action = 'skip'` **avant** de drop la colonne (sinon les skips laissent des lignes `(reaction='none', is_saved=false, read_full_article=false)` qui n'apportent rien au scoring mais polluent les `COUNT`).
- Drop la colonne `action` et son `CHECK CONSTRAINT ck_feedbacks_action`.
- ⚠️ **Migration destructive, pas de downgrade utile** : `downgrade()` peut être un `raise NotImplementedError` explicite. Documenter dans la note de release : *"backup PG recommandé avant migration"*.

**`keyword_weights`** :

- **Conserver** les colonnes `like_count` et `dislike_count` (consommées par `pwa/src/screens/Keywords.tsx:271` et `pwa/src/types/api.ts:59-60`).
- Nouveau sens :
  - `like_count` = `COUNT(*) FILTER (WHERE fb.reaction = 'like' OR fb.is_saved)`
  - `dislike_count` = `COUNT(*) FILTER (WHERE fb.reaction = 'dislike')`
- `weight` recomputé via l'expression SQL canonique ci-dessus.

**`services/weights.py`** :

- Remplacer la constante `_FEEDBACK_VALUE` par la nouvelle expression.
- Adapter `_AGGREGATE` pour les `COUNT(*) FILTER (...)`.
- Aucun autre changement structurel — le lock per-term (lignes 62-76) et l'idempotence restent identiques.

**`services/feedback_service.py` + `schemas/feedback.py`** :

- Nouveau payload :
  ```python
  class FeedbackRequest(BaseModel):
      article_id: UUID
      reaction:          Literal['like', 'dislike', 'none'] | None = None
      is_saved:          bool | None = None
      read_full_article: Literal[True]    | None = None  # monotone
  ```
- **Sémantique** : `None` (champ absent) = *ne touche pas*. `False` sur `is_saved` = *unset explicite*. `'none'` sur `reaction` = *clear*.
- Upsert partiel via un seul `INSERT … ON CONFLICT … DO UPDATE SET col = COALESCE(:val, col)` (un aller-retour DB).
- Refuser un payload où les trois champs sont `None` (400 — *no-op interdit*, signal d'un bug côté client).
- `recompute_for_terms` est appelé après upsert, identique à aujourd'hui — la liste des terms affectés ne change pas.

**Endpoints article** :

- `GET /feed`, `GET /saved`, `GET /explore/*` retournent désormais sur chaque article :
  ```json
  { "reaction": "like" | "dislike" | "none",
    "is_saved": bool,
    "read_full_article": bool }
  ```
- LEFT JOIN sur `article_feedbacks` ; défauts (`"none"`, `false`, `false`) si pas de ligne pour l'utilisateur.

**Hors scope (sera traité par S2/S4)** :

- `pwa/src/screens/Feed.tsx:267` et `pwa/src/store/feedback.ts:10,27` (logique `action === 'save'`) — restera temporairement cassé entre S1 et S2/S4. Acceptable car S1 ne déploie pas seul en prod (livraison groupée S1+S2+S4 minimum).

**MAJ docs** :

- `docs/DATA_MODEL.md` : nouveau schéma `article_feedbacks`, table de transitions, expression SQL canonique, nouveau sens de `like_count`/`dislike_count`.
- `docs/API_SPEC.md` : nouveau payload `POST /feedback`, nouveaux champs dans les réponses `/feed`, `/saved`, `/explore/*`.

**Test plan** (obligatoire — la migration est critique) :

- Unitaire `test_feedback_migration.py` : fixtures avec les 4 actions → assertions sur les colonnes après upgrade.
- Unitaire `test_feedback_partial_upsert.py` : `is_saved=True` seul ne touche pas à `reaction` ; `reaction='none'` clear sans toucher à `is_saved` ; `read_full_article=False` ignoré silencieusement ; payload vide → 400.
- Unitaire `test_weights_formula.py` : fixtures (like seul, like+save, dislike+saved, like+read, like+save+read) → poids attendus exacts.
- Intégration `test_feedback_idempotence.py` : deux appels successifs de `cron_refresh_weights` produisent les mêmes rows à la microseconde près.

**Acceptance criteria** :

- Après migration, plus aucune colonne `action` ; les feedbacks `like`/`dislike`/`save` sont convertis sans perte ; les `skip` sont supprimés.
- `POST /feedback { "article_id": ..., "is_saved": true }` ne touche pas à `reaction` ni `read_full_article`.
- `POST /feedback { "article_id": ..., "reaction": "like" }` ne touche pas à `is_saved` ni `read_full_article`.
- `POST /feedback { "article_id": ..., "read_full_article": false }` retourne 200 mais n'écrit rien (no-op silencieux côté backend — la monotonie est garantie).
- `POST /feedback { "article_id": ... }` (aucun champ) retourne 400.
- Un keyword liked + saved a un poids strictement supérieur à un keyword liked seul (1.5 × salience vs 1.0 × salience).
- `cron_refresh_weights` reste idempotent.
- `GET /feed` retourne `reaction`/`is_saved`/`read_full_article` pour chaque article ; valeurs par défaut quand pas d'interaction.

---

#### [x] E9-S2 — Feed fullscreen TikTok *(frontend)*

**Concept** : Le feed mini-carte est remplacé par un conteneur scroll-snap vertical. Chaque article occupe 100 dvh et affiche tout son contenu inline. Plus aucune navigation vers `/articles/:id` depuis le feed.

**Layout d'un slide** (réécriture de `pwa/src/screens/Feed.tsx` + nouveau composant `FeedArticleSlide.tsx` ; on s'inspire de `ArticleDetail.tsx` actuel pour le rendu interne) :

```
┌────────────────────────────────┐  ← 100dvh (pas 100vh)
│  og:image (background, blur)   │
│  + gradients haut + bas        │
│                                │
│  source badge        score     │  ← header sticky top
│                                │
│  ─── conteneur scrollable ─────│
│  Titre (24px / 600)            │
│  Keywords tags                 │
│  Summary executive (bullets)   │
│  Summary short                 │
│                                │
│  ─── contenu crawlé (si dispo) │
│  a.content rendu en markdown   │
│                                │
│  [Lire l'article complet ↗]    │  ← bouton (ouvre URL externe)
│                                │
│  ── BUTÉE ──                   │  ← cf. "Indicateur de butée"
│  ▼ logo Niouzou ▼              │
│  ── ─────────── ──             │
│                                │
│  👎      🔖      👍            │  ← actions sticky bottom
└────────────────────────────────┘
```

**Hauteur viewport — 100dvh, pas 100vh** :

- `100vh` est cassé sur Safari iOS et Chrome Android : la barre URL réduit le viewport visible, le snap déborde, le bouton actions passe sous le bord.
- Utiliser `100dvh` (dynamic viewport height). Fallback : `100svh` puis `100vh` pour les vieux navigateurs.
- Convention à documenter dans `DESIGN_SYSTEM.md` pour toutes les pages fullscreen.

**Lecture du contenu crawlé** :

- Si `article.content` est non-null (crawl réussi), il est rendu **inline avant** le bouton "Lire l'article complet". On ne perd PAS la lecture en app pour ces articles.
- Le bouton "Lire l'article complet" est toujours présent (lien externe vers `article.url`).
- Si `article.content` est null, seul le bouton est affiché — pas de bloc vide rendu.

**Scroll dual (intra-article + inter-article)** :

CSS `scroll-snap-type: y mandatory` pur ne sait pas scroller librement dans un slide puis snap au suivant. Stratégie :

1. Conteneur racine `<div class="feed-snap">` : `scroll-snap-type: y mandatory; overflow-y: scroll`.
2. Chaque slide `<article class="feed-slide">` : `scroll-snap-align: start; scroll-snap-stop: always; height: 100dvh; overflow-y: auto`.
3. Contenu intérieur `<div class="slide-scroll">` : scrollable indépendamment tant qu'on n'est pas en bas.
4. `overscroll-behavior-y: contain` sur `.slide-scroll` — quand le scroll interne touche le bas, l'inertie touch suivante traverse au parent qui snap.
5. À tester en vrai sur iOS Safari, Chrome Android et desktop. Fallback JS prévu si nécessaire : `IntersectionObserver` + bascule `scroll-snap-type: none` pendant le scroll interne.

**Indicateur de butée (visuel pédagogique — apprendre à re-scroller pour avancer)** :

À la fin du contenu scrollable du slide, juste avant le bord bas masqué par la barre d'actions, afficher un indicateur explicite :

- Nouveau composant `pwa/src/components/ScrollBoundaryHint.tsx`.
- Anatomie verticale :
  1. Fine ligne de séparation : `1px solid var(--border-subtle)`, largeur 60%, centrée, marge verticale 16px.
  2. Logomark Niouzou : réutiliser `pwa/public/favicon.svg`, 32px, `opacity: 0.6`.
  3. Chevron `ChevronDown` (lucide-react), 20px, `var(--text-tertiary)`, animation bounce :
     ```css
     @keyframes bounce-soft {
       0%, 100% { transform: translateY(0); }
       50%      { transform: translateY(4px); }
     }
     /* applied: animation: bounce-soft 1.6s ease-in-out infinite */
     ```
  4. Label *"Article suivant"* (12px, `var(--text-tertiary)`, opacity 0.5).
- Visibilité : le hint est en fin de contenu — il devient visible quand l'utilisateur a scrollé jusqu'en bas du slide. C'est intentionnel — il sert de récompense visuelle qui confirme *"tu peux re-scroller"*.
- L'animation bounce **s'arrête** dès que le slide suivant entre en viewport (économie batterie + évite sur-stimulation). Implémentation : `IntersectionObserver` sur le slide suivant → toggle `data-bouncing` sur le hint.
- À documenter dans `DESIGN_SYSTEM.md`, section "Scroll boundary".

**Actions — icônes à état** :

Barre `sticky bottom` (au-dessus de la BottomNav système), trois icônes :

- Dislike `ThumbsDown` (gauche) : `fill: var(--accent-red)` si `reaction === 'dislike'`, outline sinon.
- Save `Bookmark` (centre) : `fill: var(--accent-yellow)` si `is_saved`, outline sinon.
- Like `ThumbsUp` (droite) : `fill: var(--accent-cyan)` si `reaction === 'like'`, outline sinon.

Comportement :

- Tap like/dislike : toggle (re-tap → `reaction: 'none'`).
- Tap save : toggle `is_saved`.
- Like et dislike mutuellement exclusifs (tap like quand disliked → passe à liked, pas à `none`).
- Save et reaction indépendants.
- **Optimistic update** : l'icône change instantanément, `POST /feedback` en arrière-plan. En cas d'erreur, rollback de l'état local + toast d'erreur.
- Pas de double-tap, pas de swipe-action.

**Lecture de l'article complet** :

- Bouton "Lire l'article complet ↗" sous le contenu inline.
- `onClick` :
  1. Émettre `POST /feedback { article_id, read_full_article: true }` (fire-and-forget — la monotonie de S1 garantit que les multi-appels sont OK).
  2. `window.open(article.url, '_blank', 'noopener')`.
- L'icône reflétant `read_full_article` n'est pas exposée visuellement dans cette story — on persiste juste pour le scoring.

**Impression** :

- `IntersectionObserver` sur chaque slide (`threshold: 0.7` — ≥ 70% visible).
- Quand un slide reste ≥ 500 ms en viewport (timer `setTimeout`, annulé si l'élément ressort avant), émettre `POST /feed/:id/impression`.
- Ce seuil évite qu'un scroll rapide n'impressionne 10 articles d'affilée.
- Déduplication client (`Set<articleId>` en ref) pour éviter le double appel sur aller-retour rapide.

**Suppression** :

- Supprimer `pwa/src/screens/ArticleDetail.tsx` et la route `/articles/:id` dans `pwa/src/App.tsx:27`.
- Supprimer les `navigate('/articles/...')` :
  - `pwa/src/components/ArticleCard.tsx:112` (le composant est retiré ou refondu en `FeedArticleSlide`).
  - `pwa/src/screens/Saved.tsx:112` (cf. S4 — remplacé par navigation Explore→Feed décrite en S3).
- Conséquence : **plus de deeplink vers un article individuel**. Le partage d'URL d'article externe se fait via `article.url`, pas via une URL Niouzou. Tradeoff acté.

**Préchargement / performance** :

- `<img loading="lazy">` sur les `og:image` des slides au-delà de N+2.
- Pour slides N et N+1 : `loading="eager"` + `<link rel="preload" as="image">` injecté dynamiquement.
- Pas de virtualisation dans cette story (à reconsidérer en EPIC 10 si la pagination charge >50 slides en mémoire).

**MAJ docs** :

- `docs/DESIGN_SYSTEM.md` : layout slide fullscreen, convention `100dvh`, composant `ScrollBoundaryHint`, animation `bounce-soft`, suppression d'ArticleDetail.

**Acceptance criteria** :

- Chaque slide occupe `100dvh` ; aucune zone du contenu ou des actions n'est masquée par la barre URL Safari/Chrome.
- Le scroll dans le contenu d'un slide ne déclenche pas le snap au slide suivant tant qu'on n'a pas atteint la fin du contenu.
- Une fois le scroll interne en bout de course, un swipe vertical supplémentaire snap au slide suivant.
- L'indicateur de butée (logo Niouzou + chevron animé + label) apparaît en bas du contenu de chaque slide et anime un bounce léger jusqu'à ce que le slide suivant entre en viewport.
- Les icônes like/dislike/save reflètent l'état persisté au chargement (`GET /feed` payload S1) et se mettent à jour optimistiquement après tap.
- Save et like peuvent être actifs simultanément.
- Re-tap sur like (quand déjà liked) ramène `reaction` à `'none'`.
- "Lire l'article complet" ouvre `article.url` dans un nouvel onglet ET émet `POST /feedback { read_full_article: true }` même si l'impression n'a pas encore été enregistrée.
- L'impression d'un article n'est émise qu'après ≥ 500 ms de présence en viewport (≥ 70%).
- Un scroll-rapide à travers 5 slides n'émet pas 5 impressions instantanées (au plus l'article où l'utilisateur s'arrête).
- `pwa/src/screens/ArticleDetail.tsx` et la route `/articles/:id` n'existent plus ; `npm run build` passe sans warning d'import cassé.
- Si `article.content` est null, le bouton "Lire l'article complet" est la seule option de lecture exhaustive (pas de bloc vide rendu).

---

#### [x] E9-S3 — Explore tab *(backend + frontend)*

**Concept** : Nouvel onglet Explore (BottomNav). Deux modes — **History** (articles déjà vus, triés par `seen_at DESC`) et **New** (articles enrichis non vus, triés par le ranking gravity du feed). Permet de retrouver un article passé ou de scanner ce qui arrive sans s'engager dans le feed fullscreen.

**Backend — deux endpoints distincts** (plus propre qu'un seul `?mode=` qui mélange deux requêtes très différentes) :

- `GET /explore/history?cursor=...&limit=20`
  - Articles avec `article_impressions` pour cet utilisateur.
  - Tri : `article_impressions.seen_at DESC, articles.id DESC`.
  - Keyset cursor sur `(seen_at, id)`.
  - Chaque item : champs article + `reaction`, `is_saved`, `read_full_article`, `seen_at`.

- `GET /explore/new?cursor=...&limit=20`
  - Articles **enrichis non impressionnés** par cet utilisateur.
  - Tri : `feed_rank DESC, id DESC` (même expression que `FeedService._FEED_RANK`).
  - Keyset cursor sur `(feed_rank, id)`.
  - Hérite de `FeedService` :
    - ✅ Gravity ranking
    - ✅ Filtre `status = 'enriched'`
    - ✅ Filtre `article_impressions IS NULL`
    - ✅ Filtre `Source.user_id` (n'expose pas les sources d'autres users)
    - ❌ **Pas** de `SCORE_THRESHOLD` — Explore New montre tout l'enrichi non vu.
    - ❌ **Pas** de `random_surface_rate` — déterministe.
    - ❌ **Pas** de cold-start logic — non pertinent ici.
  - Chaque item : champs article + `reaction: 'none'`, `is_saved: false`, `read_full_article: false` (toujours ces valeurs par définition).

**Refactor `FeedService`** : extraire la requête SQL ranked (`feed_service.py:85-125`) en méthode privée `_build_ranked_query(*, apply_threshold: bool, apply_random_surface: bool)` réutilisable par `ExploreService.list_new()`.

**Pas d'auto-impression depuis Explore** :

- Scroller Explore New **n'émet aucune impression**. L'utilisateur peut scanner sans consommer.
- L'impression est émise uniquement quand l'utilisateur entre dans le feed fullscreen depuis cet article (cf. navigation ci-dessous) — code S2 s'en charge.
- Conséquence : pas de risque de "vider le feed naturel" en consultant Explore.

**Navigation Explore → Feed (tap sur un article)** :

- Route `/feed?start=:articleId` (query param, pas de path segment — évite une nouvelle route Router).
- `Feed.tsx` au mount lit `?start=` ; si présent, demande au backend la page de feed contenant cet article + place ce slide en haut.
- Backend : `GET /feed?start=:articleId` accepte un nouveau query param.
  - Si fourni, charger l'article spécifié (vérifier ownership + qu'il est `enriched`) **avant** la pagination normale.
  - Calculer son `feed_rank` ; renvoyer une première page commençant par cet article suivi des articles `(feed_rank, id) < (start.feed_rank, start.id)`.
  - Si l'article est déjà impressionné (cas Explore History), désactiver le filtre impression **pour cet article-là uniquement** : `AND (ai.article_id IS NULL OR a.id = :start)`.
- L'impression de l'article `start` sera émise normalement par S2 quand le slide reste 500 ms en viewport.

**Frontend** :

- Nouvel écran `pwa/src/screens/Explore.tsx`, route `/explore`.
- Header sticky avec deux onglets (`History` / `New`) — composant `Tabs` simple.
- Layout d'une row (reprendre la grille de `Saved.tsx`) :
  - Thumbnail og:image à gauche (64×64).
  - Titre + source au centre.
  - Score pill (relevance_score, 2 décimales).
  - Timestamp relatif (`seen_at` pour History, `published_at` pour New, format `il y a 2h`).
  - Ligne d'icônes d'état sous le titre : `Bookmark` (jaune si `is_saved`), `ThumbsUp` (cyan si liked), `ThumbsDown` (rouge si disliked), `BookOpen` (gris subtil si `read_full_article`). Outline en `var(--text-tertiary)` quand pas d'état actif.
  - En mode New, aucune icône n'a d'état actif par définition — on peut les omettre dans ce mode pour épargner le visuel.
- Tap sur une row → `navigate('/feed?start=' + article.id)`.
- Infinite scroll cursor-based (réutiliser le pattern `Saved.tsx`).
- Empty states distincts :
  - History vide : *"Aucun article lu pour l'instant. Reviens ici après avoir parcouru ton feed."*
  - New vide : *"Pas de nouveaux articles. Le prochain enrichissement est prévu dans X min."* (réutiliser `cron_enrich_interval_minutes` de `/stats`).

**MAJ docs** :

- `docs/API_SPEC.md` : endpoints `GET /explore/history`, `GET /explore/new`, nouveau query param `GET /feed?start=...`.
- `docs/DESIGN_SYSTEM.md` : pattern liste Explore (réutilise grille Saved).

**Test plan** :

- Backend `test_explore_history.py` : ordre `seen_at DESC`, cursor stable, pas de doublon.
- Backend `test_explore_new.py` : ordre gravity, pas de seuil, pas de random, n'inclut pas les impressionnés.
- Backend `test_feed_start_param.py` : article pivot en premier ; un article déjà impressionné est accepté en `start` (override d'exclusion).

**Acceptance criteria** :

- `GET /explore/history` retourne les articles vus de l'utilisateur, tri `seen_at DESC`, pagination stable.
- `GET /explore/new` retourne tous les articles enrichis non vus, tri `feed_rank DESC`, sans `SCORE_THRESHOLD` ni `random_surface_rate`.
- Scroller la liste Explore New **n'émet aucune impression** (vérifié par absence de log/insert sur `article_impressions`).
- Tap sur un article dans Explore (n'importe quel mode) ouvre le feed fullscreen avec cet article en premier slide.
- En mode History, tap sur un article déjà impressionné le ré-affiche dans le feed (override de l'exclusion par impression pour cet article).
- Les icônes d'état dans Explore History reflètent correctement `reaction`, `is_saved`, `read_full_article`.

---

#### [x] E9-S4 — Navigation & Saved update *(frontend)*

**BottomNav** (`pwa/src/components/BottomNav.tsx`) :

- Tabs finaux : **Feed** / **Explore** / **Saved** / **Profile** (4 tabs).
- Icône Explore : `Compass` (lucide-react) — plus universel que `Newspaper` et ne se confond pas avec Feed.
- Onglet Keywords retiré de la nav (route conservée, accessible via Profile).

**Profile** (`pwa/src/screens/Profile.tsx`) :

- Ajouter un menu item **"Keywords"** entre "Manage sources" et le bloc "Administration" / "System".
- Icône : `Tags` ou `Hash` (lucide-react).
- Route `/keywords` conservée, composant `Keywords.tsx` inchangé.

**Saved** (`pwa/src/screens/Saved.tsx`) :

- Source de vérité change : `SavedService` filtre désormais sur `is_saved = true` au lieu de `action = 'save'` (cohérent avec S1 — déjà couvert backend, juste à régénérer les types côté PWA).
- Chaque row affiche la même ligne d'icônes d'état qu'Explore History :
  - `Bookmark` (toujours jaune ici, par définition `is_saved = true`).
  - `ThumbsUp` (cyan si `reaction === 'like'`).
  - `ThumbsDown` (rouge si `reaction === 'dislike'`).
  - `BookOpen` (subtil si `read_full_article`).
- Tap sur une row → `navigate('/feed?start=' + article.id)` (cohérent avec Explore — supprime `navigate('/articles/:id')` ligne 112).
- Supprimer la logique snapshot `Saved.tsx:20` (revenir d'`/articles/:id`) — n'a plus de sens sans ArticleDetail.

**MAJ docs** :

- `docs/DESIGN_SYSTEM.md` : inventaire écrans + tabs nav (Feed / Explore / Saved / Profile), section "Profile menu items" (ajout Keywords).

**Acceptance criteria** :

- BottomNav affiche exactement 4 tabs : Feed / Explore / Saved / Profile.
- L'item "Keywords" est visible et fonctionnel depuis Profile.
- `Saved.tsx` charge la liste sans référence à `action = 'save'` ; les icônes d'état reflètent la réaction et le statut read.
- Tap sur un article Saved ouvre le feed fullscreen sur cet article.
- Aucun lien cassé après suppression de la route `/articles/:id` (vérifié via `npm run build` + grep `articles/` dans `pwa/src/`).

---

## EPIC 10 — Qualité du pipeline & observabilité

**Objectif** : Améliorer la qualité des résumés et des keywords générés par le LLM, donner de la visibilité sur l'avancement du pipeline d'enrichissement, et permettre de compacter les keywords dupliqués.

> Dépend de EPIC 5, EPIC 9.

**Ordre de livraison recommandé** : `S1 → S2 → S3`. S1 donne la visibilité pour diagnostiquer S2/S3 en production.

---

### Stories

#### [x] E10-S1 — Pipeline observabilité & refonte à la maille article

**Problèmes adressés** :
- "Feed may be stalled" faux positif systématique (basé sur `last_fetched_at` = dernière insertion d'article, pas dernière exécution du cron)
- Aucune visibilité sur la durée d'un run, le nombre d'articles traités, les erreurs
- `cron_fetch` et `cron_enrich` sont deux passes batch déconnectées — un article fetché attend le prochain cycle pour être enrichi
- Échec LLM transitoire (rate-limit, timeout) → fallback TF-IDF immédiat alors qu'un simple retry aurait suffi
- Article laissé en `'enriching'` après un crash du worker → jamais repêché

**Décisions produit** :
- **Backlog** : on garde le cap `enrich_batch_size` (~10). Un backlog est traité au fil des runs successifs ; durée d'un `pipeline_runs` bornée et observable.
- **Échec d'enrichissement** : pas de nouveau statut `'error'` sur `articles`. Le LLM est retenté **2 fois** (backoff 1s puis 3s) avant fallback TF-IDF. L'article passe à `enriched` avec `enrichment_method='tfidf'` et `enrichment_error` renseigné. Les rares plantages catastrophiques (extraction crash, DB error) sont comptés dans `pipeline_runs.articles_failed` sans changer le statut de l'article (laissé à `pending` pour relance au prochain run).
- **Scope `/stats`** : le bloc `pipeline` est **global** (instance-wide). Les compteurs existants (`articles`, `sources`, `keywords`) restent user-scopés. Documenté tel quel dans `API_SPEC.md`.

**Migration Alembic** :

Nouvelle table `pipeline_runs` :
```sql
id                  UUID PK
started_at          TIMESTAMPTZ NOT NULL
completed_at        TIMESTAMPTZ nullable          -- null = run en cours
status              VARCHAR NOT NULL              -- 'running' | 'completed' | 'failed'
articles_fetched    INT NOT NULL DEFAULT 0        -- nouveaux articles trouvés
articles_enriched   INT NOT NULL DEFAULT 0        -- AI ou TF-IDF, peu importe
articles_failed     INT NOT NULL DEFAULT 0        -- plantages catastrophiques
articles_in_run     INT NOT NULL DEFAULT 0        -- snapshot pending au début (figé pour la progress bar)
total_duration_s    FLOAT nullable                -- secondes
avg_s_per_article   FLOAT nullable
error               TEXT nullable                 -- si le run entier a planté
```

Index : `pipeline_runs(started_at DESC)` — toute lecture passe par cet ordre.

Pas de FK user. Pas de nouveau statut `'error'` sur `articles` — statuts inchangés : `pending` | `enriching` | `enriched`.

**Reaper au startup du worker** : avant `_scheduler.start()` dans `_lifespan`, exécuter `UPDATE articles SET status='pending' WHERE status='enriching'`. Sécurise les articles laissés en chantier par un crash précédent.

**Refonte `_run_pipeline()`** (refresh worker) :

Au lieu de deux passes batch séparées (`cron_fetch.run()` puis `cron_enrich.run()`), nouveau flow tracé via `pipeline_runs` :

1. Créer une ligne `pipeline_runs` (`status='running'`, `started_at=now()`).
2. `cron_fetch.run()` → `articles_fetched = retour de la fonction`.
3. Snapshot des `pending` capé à `enrich_batch_size` (FIFO `created_at`). Persister `articles_in_run` (figé : une fetch intermédiaire qui ajouterait des `pending` ne fait pas dériver la barre de progression).
4. Pour chaque article du snapshot :
   - `articles.status='enriching'` (transaction courte, commit immédiat — `/stats` peut voir l'avancement).
   - Enrichissement (retry LLM × 2 → fallback TF-IDF — voir bloc dédié).
   - Succès complet (AI ou TF-IDF) : `articles.status='enriched'`, incrément `articles_enriched`.
   - Exception non rattrapée : statut laissé à `pending` (repêché par le reaper au prochain run), incrément `articles_failed`.
5. Fin : `status='completed'`, `completed_at`, `total_duration_s`, `avg_s_per_article = total_duration_s / max(1, articles_enriched)`.
6. Exception globale : `status='failed'`, `error=str(e)`.

**Retry LLM** (`EnrichmentService.generate_enrichment`) :
- Tenter l'appel LLM ; sur exception, retry × 2 avec backoff (1s, 3s).
- Au 3ème échec : retour `Enrichment(keywords=None)`, le cron prend le fallback TF-IDF (comportement actuel).
- Logguer chaque tentative pour traçabilité.

Le statut `'enriching'` sur `articles` permet de calculer la progression depuis la DB sans polling — la page Profile reflète l'état réel au chargement.

**`GET /stats` — nouveaux champs** (bloc `pipeline` global) :

```json
{
  "pipeline": {
    "status": "running" | "completed" | "failed" | "never_run",
    "started_at": "2026-05-31T14:00:00Z",
    "completed_at": "2026-05-31T14:03:47Z",
    "articles_fetched": 8,
    "articles_enriched": 7,
    "articles_failed": 1,
    "total_duration_s": 227,
    "avg_s_per_article": 32.4,
    "error": null,
    "in_progress": {
      "done": 7,
      "total": 8
    }
  },
  "cron_fetch_interval_minutes": 15
}
```

`in_progress` calculé uniquement quand `status='running'` : `done = articles_enriched + articles_failed` (lus depuis la ligne `pipeline_runs`), `total = articles_in_run` (snapshot figé). Null sinon.

**Fix "Feed may be stalled"** :

Lecture de la dernière ligne `pipeline_runs` (`ORDER BY started_at DESC LIMIT 1`) :
- Aucune ligne → `status='never_run'`, pas d'alerte (instance neuve).
- `status='running'` → pas d'alerte (run en cours est sain, même long).
- `status='failed'` ET pas de `completed` plus récent → afficher `error`.
- `status='completed'` ET `completed_at < now() - 2 * cron_fetch_interval` → "stalled".

**PWA — System panel** (`Profile.tsx`) :

Remplacer "Last fetch / Next fetch / Last enrichment" par :

- **Dernier run** : timestamp relatif + durée (`"il y a 3 min · 3m 47s"`).
- **Prochain run** : `started_at + cron_fetch_interval` (calcul client basé sur `stats.cron_fetch_interval_minutes` — **supprimer la constante `CRON_FETCH_INTERVAL_MS` hardcodée** en haut du fichier).
- **Barre de progression** : visible uniquement quand `status='running'` :
  ```
  Enrichissement en cours
  ████████░░░░  7 / 8 articles
  ```
  Valeurs issues de `in_progress` dans `/stats` — pas de polling continu, refresh à l'ouverture du panel.
- **Résultats du dernier run** : `8 fetched · 7 enrichis · 1 erreur · ~32s/article`.
- **Erreur** : si `status='failed'` ou `articles_failed > 0`, afficher `error` avec timestamp — supprimer le gate `hasFallback` actuel.

**Tests** :
- Cycle de vie `pipeline_runs` : running → completed, running → failed.
- Reaper : article `'enriching'` au startup → bascule `pending`.
- 2 retries LLM avant fallback TF-IDF (mock `OpenRouterClient`, 2 levées d'exception puis succès / 3 levées puis fallback).
- `articles_failed` incrémenté sur exception non rattrapée dans `enrich_article`.
- "Stalled" off quand `status='running'`, on quand `completed_at` ancien.

**Acceptance criteria** :

- "Feed may be stalled" ne s'affiche plus quand le cron tourne normalement sans trouver de nouveaux articles.
- Après un run : durée, articles fetched/enrichis/en erreur et moyenne par article affichés dans le System panel.
- Pendant un run : la barre de progression affiche l'avancement réel depuis la DB, ne dérive pas si une fetch intermédiaire ajoute des `pending`.
- Un article fetché dans le même cycle est enrichi dans la même exécution (dans la limite de `enrich_batch_size`).
- Crash worker pendant enrichissement → article repêché au prochain run via le reaper.
- Un échec LLM transitoire est retenté (× 2) avant fallback TF-IDF.
- `pipeline_runs` conserve l'historique des runs (index `started_at DESC`).
- Docs mises à jour : `docs/DATA_MODEL.md` (table `pipeline_runs`, statut `'enriching'`), `docs/API_SPEC.md` (champs `/stats`, scope global du bloc `pipeline`), `docs/ARCHITECTURE.md` (refresh-worker porte la lifecycle des `pipeline_runs` et le reaper).

---

#### [x] E10-S2 — Qualité des résumés : prompt + debug score

**Problèmes adressés** :
- `summary_executive` s'affiche sous forme `['texte...']` quand le LLM retourne un tableau JSON
- Résumé parfois en anglais pour un article français
- Keywords trop événementiels et non réutilisés entre articles ("défaite", "centre argentin")
- Impossible de savoir quel modèle a enrichi un article donné

**Fix parsing `summary_executive`** (`enrichment_service.py:_parse_enrichment`) :

Gérer le cas où le LLM retourne un tableau :

```python
executive = data.get("summary_executive")
if isinstance(executive, list):
    executive = "\n".join(f"- {item}" for item in executive if item)
elif executive:
    executive = str(executive).strip()
```

`ExecutiveSummary` côté PWA splitte déjà sur `\n` (`FeedArticleSlide.tsx:425`), aucun changement frontend nécessaire. Tests unitaires sur `_parse_enrichment` : string, list, list vide, list imbriquée (drop silencieux).

**Fix langue** :

Heuristique légère sur stop-words (fr / en / es / de / pt) — pas de lib externe. Appliquée à `title + content[:500]` (le titre seul est souvent trop court / ambigu). Si aucune langue ne ressort (compteurs nuls ou égalité), fallback à la consigne actuelle.

```python
lang = _detect_language(title, content)  # None si indétecté
header = f"Language: {lang}\n" if lang else ""
body = f"{header}Title: {title}\n\n{content[:_MAX_INPUT_CHARS]}"
```

System prompt : remplacer `"Write in the article's language"` par `"Respond in the language specified in the 'Language:' field, or in the article's language if unspecified."`.

**Amélioration prompt keywords** :

1. Guider vers des concepts stables — ajouter au `_ENRICHMENT_SYSTEM` :
> *"keywords should be stable reusable concepts — prefer named entities (clubs, countries, people, companies), domains (football, AI, finance) and topics (climate, elections) over ephemeral events or actions ('defeat', 'final', 'Argentine midfielder'). Normalise names consistently."*

2. Injection du vocabulaire existant (top 200 terms par fréquence dans `article_keywords`) dans le prompt user :

```python
vocab = await _load_top_keywords(db, limit=200)
if vocab:
    body = f"Existing vocabulary (reuse when applicable): {', '.join(vocab)}\n" + body
```

**Cache vocab** : chargé **une fois par `cron_enrich.run()`** (cache sur `EnrichmentService`, rechargé en tête de chaque run), pas à chaque article. Évite ~1.5–3k tokens × N articles par run sur la prompt cache miss.

**Stockage du modèle utilisé** :

- Alembic : ajouter `enrichment_model VARCHAR nullable` sur `articles`.
- Path AI réussi : `article.enrichment_model = settings.openrouter_model` (modèle effectif au moment du run).
- Path TF-IDF (fallback ou natif) : laisser `enrichment_model = NULL` — `enrichment_method='tfidf'` indique déjà la méthode, dupliquer dans deux colonnes serait redondant.
- Exposer `enrichment_model` dans `GET /feed`, `GET /explore/*`, `GET /saved`.

**PWA — debug panel score badge** :

Tap sur le score badge (feed slide + Explore + Saved) → bottom sheet :

```
Score 0.74 · AI · gemma-4-28b

football              +1.2
FC Barcelone          +0.8
Ligue des Champions    —
```

Dash quand le keyword n'a pas encore de poids user.

**UX critique** : le handler du badge appelle `e.stopPropagation()` pour ne pas déclencher les gestures TikTok du slide ni la navigation détail.

**Backend** : `GET /articles/:id/score-debug` — authentifié **et propriétaire de l'article** (via `source.user_id`). Retourner `403` sinon : ne jamais exposer les `keyword_weights` cross-user.

```json
{
  "relevance_score": 0.74,
  "scorer": "ai_keyword",
  "enrichment_model": "google/gemma-4-28b",
  "keywords": [
    { "term": "football", "weight": 1.2 },
    { "term": "fc barcelone", "weight": 0.8 },
    { "term": "ligue des champions", "weight": null }
  ]
}
```

`weight: null` = keyword présent sur l'article mais aucun row `keyword_weights` pour cet user (sémantiquement neutre = 0, mais distingué dans l'UI par le dash).

**Tests** :
- `_parse_enrichment` : string, list, list vide, list imbriquée.
- `/score-debug` : 403 cross-user, 200 owner, `weight: null` quand absent.
- Détection langue : article fr + 2 stop-words en → détecté `fr` ; égalité parfaite → `None`.

**Acceptance criteria** :

- `summary_executive` ne s'affiche plus jamais sous forme `['...']`.
- Article français enrichi → résumé et bullets en français.
- Keywords générés contiennent des entités et domaines stables — plus de "défaite", "finale", "centre argentin".
- Le LLM reçoit les 200 keywords existants les plus fréquents (cache par run) et réutilise les termes connus quand applicable.
- Score badge tappable ; panel affiche modèle, scorer, keywords + poids (null si pas encore de poids). Le tap n'interfère pas avec les gestures du slide.
- `enrichment_model` présent sur tous les articles nouvellement enrichis via AI ; `NULL` sur path TF-IDF.
- `/score-debug` refuse l'accès cross-user (403).
- Docs mises à jour : `docs/DATA_MODEL.md` (colonne `enrichment_model`), `docs/API_SPEC.md` (endpoint `/articles/:id/score-debug`, champ `enrichment_model` dans feed/explore/saved).

---

#### [x] E10-S3 — Compaction & refresh des keywords

**Problème adressé** :
- Des keywords sémantiquement identiques coexistent sous des formes différentes ("FC Barcelone", "Barcelona FC", "Barça") → poids éclatés, signal dilué pour le scoring.

**Décisions produit** :
- **Chunking** : top N par fréquence en **un seul appel LLM** (N par défaut = 500 via `COMPACTION_TOP_N`). La longue traîne (terms rares) est ignorée volontairement — c'est là où la dilution de signal fait le moins mal et où le ratio bénéfice/coût LLM est le plus faible.
- **Safety — deux étapes preview/apply** : aucune modification de la DB tant que l'admin n'a pas validé les groupes proposés. Un preview reste applicable ultérieurement tant qu'il n'a pas été rejeté.
- **Implémentation côté refresh-worker** : la compaction réutilise le pattern de `POST /admin/refresh` (E7-S16/E8-S6) — l'API proxy vers le worker pour ne pas étouffer uvicorn pendant la phase LLM + `cron_refresh_weights` (plusieurs minutes possibles).
- **Pin users préservés** : les groupes contenant un term `manually_overridden=true` dans `keyword_weights` sont **skipés** à l'apply (pas d'écrasement silencieux d'un choix explicite).

**Migration Alembic** :

Nouvelle table `compaction_runs` :
```sql
id                UUID PK
created_at        TIMESTAMPTZ NOT NULL
applied_at        TIMESTAMPTZ nullable     -- null = preview non encore appliqué
status            VARCHAR NOT NULL         -- 'preview' | 'applied' | 'rejected' | 'failed'
groups_json       JSONB NOT NULL           -- [{"canonical": "...", "aliases": [...], "skipped_reason": "..."?}]
keywords_merged   INT NOT NULL DEFAULT 0   -- somme des aliases effectivement fusionnés à l'apply
error             TEXT nullable
```

Index : `compaction_runs(created_at DESC)`.

Pas de réutilisation de `pipeline_runs` — sémantiquement distinct (lifecycle preview/apply ≠ run pipeline), évite de renommer/surcharger `articles_fetched`.

**Worker — endpoints** :

- `POST /compact/preview` (utilise un `_compact_lock` **séparé** du `_lock` pipeline, pour ne pas geler l'enrichissement pendant l'appel LLM) :
  1. Charger top N terms : `SELECT term, COUNT(*) AS n FROM article_keywords GROUP BY term ORDER BY n DESC LIMIT :n`.
  2. Appel LLM : *"Group these terms by semantic equivalence. Return only groups with 2+ members."*
  3. Persister `compaction_runs(status='preview', groups_json=...)`.
  4. Retour `{"id", "groups"}`.

- `POST /compact/apply` body `{"id": "..."}` (utilise le `_lock` **partagé** avec le pipeline — apply bloque/est bloqué par un run en cours, sinon les UPDATE+refresh peuvent corrompre un run d'enrichissement simultané) :
  1. Charger `compaction_runs` par id, vérifier `status='preview'`.
  2. Annoter `groups_json` : pour chaque groupe contenant un term avec `manually_overridden=true`, ajouter `skipped_reason="pinned"` et exclure du traitement.
  3. Pour chaque groupe non skipé :
     - **Résoudre les collisions PK `(article_id, term)`** : si un article a déjà `canonical` ET un alias, garder une seule row avec `salience = MAX(...)` (`DELETE` des doublons) **avant** `UPDATE article_keywords SET term = canonical WHERE term IN (aliases)`.
  4. Déclencher `cron_refresh_weights.run()` (recompute depuis `article_feedbacks × article_keywords` avec terms canoniques).
  5. **Purge des orphelins** : `DELETE FROM keyword_weights WHERE term NOT IN (SELECT DISTINCT term FROM article_keywords) AND manually_overridden = false`. Refaire la purge une 2ᵉ fois après ~100 ms — un `POST /feedback` arrivé pendant la fenêtre peut recréer un row sur un alias maintenant orphelin.
  6. `status='applied'`, `applied_at=now()`, `keywords_merged = somme(len(aliases))` sur les groupes non skipés.
  7. Sur exception : `status='failed'`, `error=str(e)`.

**API** :

- `POST /admin/compact-keywords/preview` (require_admin) : proxy vers worker. Retour `202` + `{"id", "groups"}` (le PWA affiche les groupes).
- `POST /admin/compact-keywords/apply` body `{"id"}` (require_admin) : proxy vers worker. Retour `202` + `{"status": "started"|"already_running"}`.
- `DELETE /admin/compact-keywords/{id}` (require_admin) : marque le preview `status='rejected'` (housekeeping si l'admin annule sans appliquer).
- `GET /stats` : ajouter `last_compact_at` (`MAX(applied_at)` sur `compaction_runs`), `distinct_keyword_count` (`COUNT(DISTINCT term) FROM article_keywords`), `pending_compaction_id` (id du preview le plus récent en attente, null sinon).

**PWA — Admin screen** :

Nouvelle section "Keywords" (sous Users) :

- Statistiques : `distinct_keyword_count`, `last_compact_at` (format relatif).
- Bouton **"Analyser la compaction"** : appel preview, ouvre un modal scrollable avec les groupes proposés (canonical en gras, aliases en italique, groupes skipés grisés avec mention "épinglé").
- Modal : bouton **"Appliquer"** + bouton **"Annuler"** (DELETE preview).
- Sur Appliquer : POST apply, bouton "En cours…", refresh `/stats` après 10 s.
- Si `pending_compaction_id` non null au mount : proposer "Reprendre la dernière analyse" (skip preview, ouvre directement le modal sur le preview existant).

**Tests** :
- Collision PK : article ayant déjà `canonical` + alias → DELETE + MAX salience, pas de violation à l'UPDATE.
- Group contenant `manually_overridden=true` → skipé à l'apply, pin préservé, annoté `skipped_reason='pinned'`.
- Purge orphelins : feedback concurrent recrée un row sur un alias en cours de purge → 2ᵉ passe nettoie.
- Preview idempotent : 2 previews successifs sans apply ne corrompent rien (le dernier `preview` reste celui pointé par `pending_compaction_id`).
- API : lock partagé avec pipeline (apply pendant un run → `already_running`).

**Acceptance criteria** :

- Après apply, des terms comme "FC Barcelone" et "Barcelona FC" n'ont plus qu'une seule entrée dans `article_keywords` (sauf si l'un d'eux est pinned).
- Les poids user pour les aliases sont recalculés via `cron_refresh_weights` — aucune contribution n'est perdue sur les groupes appliqués.
- Les lignes alias orphelines dans `keyword_weights` sont supprimées après le refresh (double passe anti-race).
- `cron_refresh_weights` schedulé quotidiennement reste inchangé — la compaction est un déclenchement on-demand supplémentaire qui enchaîne sa propre passe de refresh.
- Le bouton admin est protégé par confirmation (modal montrant les groupes) et par le lock partagé avec le pipeline.
- `last_compact_at`, `distinct_keyword_count`, `pending_compaction_id` visibles dans la section Keywords de l'admin.
- Aucun term `manually_overridden=true` n'est silencieusement écrasé ; les groupes affectés sont visibles dans `groups_json.skipped_reason`.
- Docs mises à jour : `docs/API_SPEC.md` (endpoints preview/apply/delete, champs `/stats`), `docs/DATA_MODEL.md` (table `compaction_runs`).

---

#### [x] E10-S4 — Articles cold-start : badge « New » + bypass threshold

**Problème adressé** :

Quand un article a des keywords que l'utilisateur n'a jamais rencontrés, le
scorer (TF-IDF ou AI) retourne ~0.5 — la valeur « neutre » qui sort quand
aucun signal user n'est disponible. Conséquences :

- L'utilisateur règle `score_threshold` à 70 % → tous les nouveaux articles
  passent sous le seuil et **disparaissent du feed** sans avoir eu la chance
  d'être évalués (chicken-and-egg : pas de feedback possible si l'article
  n'apparaît jamais).
- Le `50 %` affiché sur le badge est trompeur. Ce n'est pas « 50 % de chance
  d'aimer », c'est « je ne sais pas ». Un user ne distingue pas un article
  réellement moyen d'un article inédit.

**Décisions actées** :

| Question | Décision |
|---|---|
| Critère cold | **Aucun** des keywords de l'article n'a de row dans `keyword_weights` pour ce user. |
| Stockage | Colonne `is_cold_start BOOLEAN` sur `article_relevance_scores`, stampée à l'enrichissement. |
| Décommission | Dans `cron_refresh_weights` (quotidien) — après recompute des poids, batch UPDATE des rows dont au moins un keyword a maintenant un poids. |
| Bypass threshold | **Complet** — les cold articles passent quel que soit `score_threshold` (pas de quota). |
| Position feed | Triés comme si leur score effectif était ~0.5 — entre les bons et les mauvais. |
| Badge | Texte `New` (anglais, court) à la place du `X %`. Tap → score-debug comme d'habitude. |
| Score-debug | Pas de header spécial : la liste affiche déjà les keywords avec `—` (poids null) ; le signal visuel est suffisant. |
| `RANDOM_SURFACE_RATE` | Inchangé — la sémantique est différente (exploration aléatoire vs collecte de feedback sur l'inédit). |

**Migration Alembic** :

Ajouter sur `article_relevance_scores` :

```sql
is_cold_start BOOLEAN NOT NULL DEFAULT FALSE
```

Pas d'index dédié — la colonne est lue à chaque ligne déjà projetée dans
`ranked_query`, et écrite uniquement par le batch de décommission (qui scan
les rows `is_cold_start = TRUE`).

Backfill au upgrade : `UPDATE … SET is_cold_start = TRUE WHERE NOT EXISTS
(SELECT 1 FROM article_keywords ak JOIN keyword_weights kw ON kw.term = ak.term
AND kw.user_id = article_relevance_scores.user_id WHERE ak.article_id =
article_relevance_scores.article_id)`. Précautionneux : un upgrade sur instance
chargée tournera longtemps — `RUN_BACKFILL=1` env var optionnelle, ou skip
backfill et laisser le cron stamper progressivement les nouveaux articles
(les anciens passent en tant que non-cold, ce qui est dégradé mais pas
catastrophique).

**Scoring (`api/niouzou/scoring/`)** :

Au moment où `ScoringPipeline` calcule le score pour un (user, article), on
calcule aussi `is_cold_start` :

```python
# Dans le service qui upsert article_relevance_scores
known_terms = set(
    await session.execute(
        select(KeywordWeight.term)
        .where(KeywordWeight.user_id == user_id)
        .where(KeywordWeight.term.in_(article_terms))
    ).scalars().all()
)
is_cold = not known_terms  # vrai ssi 0 keyword de l'article connu
```

Le `is_cold_start` est stampé à chaque upsert (initial à l'enrichissement,
et à chaque recalcul `cron_refresh_weights`).

**`cron_refresh_weights` — passe de décommission** :

Après le recompute global des `keyword_weights` (qui crée potentiellement
de nouvelles rows pour des termes qui étaient inconnus), démoter les flags
devenus stale :

```sql
UPDATE article_relevance_scores ars
SET is_cold_start = FALSE
WHERE ars.is_cold_start = TRUE
  AND EXISTS (
    SELECT 1
    FROM article_keywords ak
    JOIN keyword_weights kw
      ON kw.term = ak.term AND kw.user_id = ars.user_id
    WHERE ak.article_id = ars.article_id
  );
```

Cas symétrique (warm → cold) ignoré : la suppression d'un row
`keyword_weights` est rarissime (compaction E10-S3 ne touche que les aliases,
et les pinned ne sont jamais supprimés). Si un edge case force un re-cold,
il sera rattrapé au prochain enrichissement de cet article.

**`ranked_query` (feed + explore)** :

Deux changements dans `services/ranked_query.py` :

1. **Projection** : ajouter `ars.is_cold_start AS is_cold_start` aux
   `RANKED_COLUMNS` et au `row_to_article` (vers le schema `FeedArticle`).
2. **Bypass threshold** :

```sql
WHERE (ars.relevance_score >= :threshold OR ars.is_cold_start = TRUE)
```

3. **Tri** : `ORDER BY (CASE WHEN ars.is_cold_start THEN 0.5
   ELSE ars.relevance_score END) DESC` pour positionner les cold autour de la
   mi-classement.

Note : le bypass complet signifie que pour `threshold = 1.0` (impossible en
pratique), seul un cold passerait. Acceptable — c'est la sémantique demandée.

**Schemas** :

`schemas/feed.py` :

```python
class FeedArticle(BaseModel):
    ...
    is_cold_start: bool = False  # E10-S4 — true ssi aucun keyword n'a de poids user
```

Idem côté `pwa/src/types/api.ts`.

**PWA** :

- `ScoreBadge` : si `is_cold_start === true`, afficher un tiret `–` au lieu du
  pourcentage (style identique au % — même fond accent, même tap target).
  L'icône Sparkles reste affichée si scorer == AI (donc un article cold
  AI-enriched affiche `– ✨`). Le tiret évite la confusion avec un "nouvel
  article" fraîchement ingestié — deux concepts distincts.
- `ScoreDebugSheet` : aucune modif spécifique — les keywords s'affichent
  déjà avec `—` (poids null) pour un user sans signal, et le header
  `Score — · AI · …` rend correctement le `relevance_score: null`.
- `FeedArticleSlide`, `ArticleListRow`, `SavedRow`, etc. : aucune logique
  conditionnelle — le badge gère tout.

**Tests** :

Backend :
- Article avec 3 keywords inconnus → `is_cold_start = TRUE`.
- Article avec 1 keyword connu (même à poids 0.0001) + 2 inconnus →
  `is_cold_start = FALSE` (« aucun keyword connu » est strict).
- `cron_refresh_weights` démote `is_cold_start` quand un nouveau
  `keyword_weight` apparaît sur un term partagé.
- `/feed?min_score=0.9` retourne quand même les cold articles ; vérifier
  qu'ils sont positionnés autour du milieu de la page (pas en tête, pas en
  queue).
- `/articles/:id/score-debug` renvoie `relevance_score: null`/score brut +
  keywords avec `weight: null` quand cold ; pas de champ dédié.

Frontend :
- `ScoreBadge is_cold_start={true}` rend « New » au lieu du %.
- Tap sur badge cold ouvre quand même le ScoreDebugSheet.

**Acceptance criteria** :

- Article dont aucun keyword n'a de row dans `keyword_weights` pour le user
  → badge `New` (et plus jamais `50 %`).
- Threshold à 70 % : les cold articles apparaissent quand même dans le feed.
- Les cold articles ne squattent pas le top de la page — ils s'intercalent
  autour du score 0.5 (entre bons et mauvais).
- Un feedback sur un keyword d'un cold article → au prochain
  `cron_refresh_weights` (nuit), l'article (et ses pairs partageant ce
  keyword) basculent en warm et affichent un % réel.
- Backfill : sur une instance existante, après migration, tous les articles
  sans signal user ont `is_cold_start = TRUE` ; les autres restent à
  `FALSE`. (Ou skip backfill assumé — à décider à l'exécution.)
- Pas de changement sur `RANDOM_SURFACE_RATE` — le mécanisme d'exploration
  aléatoire continue de fonctionner indépendamment.
- Docs mises à jour : `docs/DATA_MODEL.md` (colonne `is_cold_start`),
  `docs/API_SPEC.md` (champ `is_cold_start` dans `/feed`, `/explore/*`,
  `/saved`).

---

#### [x] E10-S5 — System panel : agrégats pipeline « Last X hours »

**Problème adressé** :

Le bloc System actuel affiche les compteurs du **dernier run pipeline**
(``fetched=8 enriched=7 failed=0, ~32s/article``). C'est une photo
instantanée — sur une instance qui tourne toutes les 15 min, ce sont
souvent des chiffres minuscules (1-2 articles), et le run précédent peut
être très différent (10 articles avec 1 erreur). Pas de vue agrégée pour
juger de la santé du pipeline sur les dernières heures.

Le ``last_error`` qui restait affiché 3 h après une erreur est traité
indépendamment (auto-hide après 1 h, déjà livré dans la même PR que cette
spec).

**Décisions actées** :

- **Remplacer** le bloc "Last run" — pas de double affichage. Le run
  individuel reste accessible si besoin via Railway logs ; l'écran admin
  doit privilégier la santé agrégée.
- Window picker à **3 positions** : ``1h | 6h | 24h``. Default ``6h`` —
  assez large pour lisser les runs courts (4-6 cycles à 15 min), assez
  étroit pour refléter l'état actuel.
- Agrégats fournis : ``runs_count``, ``articles_fetched``,
  ``articles_enriched``, ``articles_failed``, ``avg_s_per_article``. Pas
  besoin de plus.
- Pas de stockage supplémentaire — tout se calcule depuis ``pipeline_runs``.

**Backend** :

Nouveau champ sur ``StatsResponse.pipeline`` :

```python
class PipelineAggregates(BaseModel):
    window_hours: int          # echoes the query param
    runs_count: int
    articles_fetched: int
    articles_enriched: int
    articles_failed: int
    avg_s_per_article: float | None  # null when no run completed in the window

class PipelineStats(BaseModel):
    # … existing fields (status, started_at, etc., in_progress) …
    aggregates: PipelineAggregates
```

Endpoint ``GET /stats`` accepte un nouveau query param :

```
GET /stats?pipeline_window=6h
```

Valeurs acceptées : ``1h``, ``6h``, ``24h``. Default ``6h``. Validation
stricte (rejet 422 sur autre valeur — évite l'injection SQL via interval
string).

Calcul SQL (un seul aller-retour) :

```sql
SELECT
    COUNT(*) AS runs_count,
    COALESCE(SUM(articles_fetched), 0) AS articles_fetched,
    COALESCE(SUM(articles_enriched), 0) AS articles_enriched,
    COALESCE(SUM(articles_failed), 0) AS articles_failed,
    -- Moyenne pondérée par articles_enriched, pas moyenne des moyennes :
    -- un run avec 10 articles compte 10× plus qu'un run avec 1.
    NULLIF(SUM(total_duration_s), 0)
        / NULLIF(SUM(articles_enriched), 0) AS avg_s_per_article
FROM pipeline_runs
WHERE started_at > now() - :window
  AND status = 'completed';  -- les runs failed/running ne polluent pas la moyenne
```

**PWA — System panel** :

Remplacer le bloc actuel par :

```
Pipeline · Last  [1h] [6h] [24h]
                       ───
12 runs · 84 fetched · 79 enriched · 5 failed · ~29s/article
```

Toggle 3 boutons ; le sélectionné a le fond accent. Au tap, refetch
``/stats?pipeline_window=…`` — pas de cache local plus malin que ça,
``/stats`` est déjà rapide.

Le statut du run en cours (« Enrichissement en cours · 3/10 articles »
quand ``status='running'``, depuis E10-S1) reste affiché **au-dessus** du
bloc agrégats — c'est une info temps-réel utile et distincte des
agrégats historiques.

**Tests** :

- Endpoint avec ``?pipeline_window=1h`` retourne uniquement les runs de la
  dernière heure.
- Window invalide (ex. ``?pipeline_window=2h``) → 422.
- ``avg_s_per_article`` = ``null`` quand aucun run ``completed`` dans la
  fenêtre.
- La moyenne est pondérée par ``articles_enriched`` (un run avec 10
  articles à 30 s contribue 10× plus qu'un run avec 1 article à 60 s).
- Aucun run dans la fenêtre → tous les compteurs à 0, ``runs_count = 0``.

**Acceptance criteria** :

- Le bloc « Last run » disparaît du System panel ; remplacé par
  « Pipeline · Last X » avec picker.
- Default 6 h ; le user peut passer à 1 h ou 24 h sans rafraîchir la page.
- Les compteurs sont des sommes sur la fenêtre, pas le dernier run isolé.
- ``avg_s_per_article`` est pondérée par le nombre d'articles, pas une
  moyenne arithmétique.
- Docs mises à jour : ``docs/API_SPEC.md`` (param ``pipeline_window``,
  nouveau bloc ``aggregates``).

---

#### [x] E10-S6 — Détection du contenu boilerplate (paywall/CGU) & fallback RSS

**Problème adressé** :

Pour les sources fortement paywallées, ``newspaper4k`` renvoie parfois un
texte **non-vide** mais qui n'est pas l'article : le footer RGPD/CGU du
site, ou un message de cookie-wall. Ce texte poubelle :

- est stocké dans ``article.content`` et affiché tel quel dans la PWA
  (sous le résumé IA, ``FeedArticleSlide.tsx``) ;
- est envoyé au LLM pour générer ``summary_executive`` → résumé
  **halluciné**, cohérent avec le titre (présent dans le prompt) mais sans
  rapport avec le contenu réellement fourni ;
- échappe au détecteur ``is_premium`` (``content < premium_content_max_chars``
  = 800) car le pavé RGPD fait ~1000 caractères → pas d'icône 🔒 alors que
  le contenu est inutilisable.

Constaté en prod sur la source **Le Progrès** (``edition-lyon-villeurbanne/rss``) :
**190 / 269 articles (71 %)** ont exactement le même pavé RGPD de 1002
caractères (texte fixe du groupe EBRA — ``"Le Progrès, en tant que
responsable de traitement... Délégué à la Protection des Données
personnelles (dpo@ebra.fr)..."``) comme ``content``, et les 269 ont un
``summary_executive`` généré.

Le ``<description>`` du flux RSS contient déjà, pour ces mêmes articles,
l'extrait gratuit réel de la page (~150-300 caractères, identique au texte
de la div ``preview``/``non-paywall2`` côté site) — mais il n'est utilisé
comme ``rss_fallback`` que si ``newspaper4k`` renvoie un texte **vide** ou
lève une exception (``enrichment_service.py:193-213``). Ici l'extraction
« réussit » avec du contenu poubelle, donc le fallback RSS n'est jamais
déclenché et l'extrait utile est jeté.

**Décision produit** : ne pas couper la source — 29 % des articles « Le
Progrès » ont un vrai contenu exploitable (galeries « En images », infos
trafic...). On corrige l'extraction pour ces 71 % d'articles paywall.

**Implémentation** :

Détection à **deux niveaux**, pour limiter le risque de faux positif sur un
article dont le *sujet* serait justement le RGPD, la CNIL ou les cookies
(ex. un article sur une sanction CNIL ne doit pas être traité comme du
boilerplate juste parce qu'il contient le mot « RGPD ») :

1. **Match exact** (texte normalisé : ``\xa0``/espaces multiples collapsés,
   trim) contre une liste de **templates complets connus** — couvre le pavé
   RGPD EBRA (1002 car., identique sur 190/269 articles « Le Progrès ») et
   le message cookie-wall. Risque de faux positif quasi nul : un article
   réel n'est jamais mot-pour-mot identique à un footer CMS/RGPD.
2. **Marqueurs spécifiques** (substrings, insensibles à la casse, **tous**
   requis dans un même groupe) — filet de sécurité pour des variantes
   tronquées du même template. On n'utilise **aucun mot générique lié au
   thème** (``"RGPD"``, ``"protection des données"``, ``"cookies"``...) qui
   pourrait apparaître dans un vrai article traitant de ce sujet. Seules des
   chaînes **propres au template CMS/EBRA**, improbables dans une prose
   journalistique : ``"dpo@ebra.fr"`` ; ou le groupe
   (``"Service Relations Clients"`` ET ``"abonnements et autres services
   souscrits"``) ; ou ``"lprventesweb@leprogres.fr"``.

**Config extensible** (``config.py``) — deux nouveaux settings, chaînes
avec séparateur ``|||`` (peu probable dans du texte FR, facile à saisir
dans Railway), fusionnées avec les listes intégrées par défaut :

```python
# Pipe-separated (|||) extra boilerplate signatures (E10-S6), merged with
# the built-in EBRA/cookie-wall lists in enrichment_service.py. Lets an
# operator add a new paywall/CGU signature without a code change when one
# slips through. `_exact` = full normalized-text match (near-zero false
# positives). `_markers` = groups of substrings that must ALL co-occur —
# avoid generic RGPD/cookies vocabulary that could appear in a legitimate
# article about that topic; prefer source-specific strings (emails,
# CMS-only phrasings). Groups within `_markers` are separated by `|||`,
# substrings within a group by `&&`.
enrichment_boilerplate_exact: str = ""
enrichment_boilerplate_markers: str = ""
```

``_is_boilerplate(text: str) -> bool`` (dans ``enrichment_service.py``)
combine les listes intégrées (codées en dur) avec ces deux settings parsés
au chargement, et renvoie ``True`` si le texte matche un template exact OU
si tous les marqueurs d'un même groupe sont présents.

- Dans ``extract_content`` : si ``parsed.text`` est non-vide **mais**
  ``_is_boilerplate(text)`` est vrai, traiter comme un échec d'extraction
  (même branche que texte vide / exception) → fallback sur
  ``rss_fallback`` via ``_strip_html``.
- Effet de bord recherché : ``content`` devient l'extrait RSS
  (~150-300 car.), donc ``< premium_content_max_chars`` (800) →
  ``is_premium`` se déclenche correctement (icône 🔒 affichée).

**Backfill** : nouveau script one-shot ``api/niouzou/tools/backfill_boilerplate_content.py``
(même pattern que ``tools/backfill_embeddings.py``) — pour chaque article
dont ``content`` matche ``_is_boilerplate``, ré-extraire via
``EnrichmentService.extract_content`` (avec le ``content`` Miniflux brut
comme ``rss_fallback``), puis ré-enrichir (``generate_enrichment``) et
recalculer l'embedding. Limité aux articles dans
``SMART_RESCORE_WINDOW_DAYS`` ou via un flag ``--all``.

**Tests** :

- ``_is_boilerplate`` détecte le pavé RGPD EBRA exact (match exact normalisé)
  et la variante cookie-wall ; ne faux-positive pas sur un extrait d'article
  réel court (ex. les contenus de 263-450 car. observés sur « Le Progrès »).
- **Anti faux-positif thématique** : un article réel *sur* le RGPD/CNIL/les
  cookies (texte journalistique contenant les mots « RGPD », « protection
  des données », « cookies », « CNIL »... mais sans les marqueurs
  CMS/EBRA et sans match exact) → ``_is_boilerplate`` renvoie ``False``,
  le contenu est conservé tel quel.
- Marqueurs config (``enrichment_boilerplate_markers``) : un groupe ne
  matche que si **toutes** ses sous-chaînes sont présentes — un texte ne
  contenant qu'une seule des deux ne déclenche pas le filtre.
- ``extract_content`` : ``newspaper4k`` renvoie le pavé RGPD →
  ``rss_fallback`` est utilisé, pas le pavé.
- ``extract_content`` : ``newspaper4k`` renvoie un vrai texte court (non
  boilerplate) → conservé tel quel (pas de fallback intempestif).
- ``generate_enrichment`` reçoit l'extrait RSS comme ``content`` (test
  avec fake LLM — vérifie que le bon texte est passé en input du prompt).

**Acceptance criteria** :

- Nouveaux articles « Le Progrès » paywallés : ``content`` = extrait RSS
  (pas le pavé RGPD/cookie-wall), ``is_premium=true``,
  ``summary_executive`` cohérent avec cet extrait.
- Backfill exécuté sur les ~190 articles existants concernés.
- ``docs/CONVENTIONS.md`` documente le détecteur de boilerplate et son
  caractère best-effort/extensible (liste de patterns à enrichir si
  d'autres sources paywall sont ajoutées).

---

#### [x] E10-S7 — System panel : suivi du coût OpenRouter (1h/6h/24h)

**Problème adressé** :

Aucun suivi de la facture OpenRouter — l'admin ne sait pas combien coûte
l'enrichissement sans aller consulter le dashboard OpenRouter externe.

**Décisions actées** :

- Affichage **$ seul** (pas de tokens, pas de nombre d'appels) — un chiffre
  simple par fenêtre.
- Périmètre : appels LLM d'**enrichissement uniquement**
  (``cron_enrich`` / refresh worker, via ``enrichment_resources``) — pas les
  appels de compaction admin (E10-S3).
- Les 3 fenêtres ``1h | 6h | 24h`` sont affichées **ensemble**, sans picker
  (contrairement à E10-S5) — pas besoin de toggle pour 3 nombres.

**Implémentation** :

Le SDK OpenRouter installé (v0.9.1) ne renseigne pas ``usage.cost`` sur la
réponse de chat completion (champ absent du modèle Pydantic ``ChatUsage``).
Le coût réel est récupéré via un appel best-effort à l'endpoint
``/generation`` (``client.generations.get_generation(id=response.id)`` →
``data.total_cost``), juste après chaque ``complete()`` réussi
(``OpenRouterClient._record_usage``). Un échec de ce lookup (404 transitoire
pendant qu'OpenRouter finalise ses stats) est juste loggé en debug — n'affecte
jamais l'enrichissement.

Nouvelle table ``llm_usage_log`` (une ligne par completion réussie — modèle,
``cost_usd``, ``prompt_tokens``, ``completion_tokens``, ``created_at``).
``OpenRouterClient`` accumule les ``UsageRecord`` dans ``self.usage_log``
pendant un run ; ``enrichment_resources`` (chokepoint unique du cycle de vie
du client pour ``cron_enrich`` et le refresh worker) flush cette liste vers
``llm_usage_log`` dans son ``finally``, après chaque run.

``GET /stats`` gagne un bloc ``llm_cost.windows`` — somme de
``llm_usage_log.cost_usd`` sur 1h/6h/24h via une seule requête à agrégation
conditionnelle (``CASE WHEN ... THEN cost_usd END``, même pattern que
``_pipeline_aggregates`` de E10-S5).

**PWA — System panel** :

Nouveau bloc sous les agrégats pipeline :

```
Coût OpenRouter
1h · $0.0042   6h · $0.0218   24h · $0.0871
```

Affiché sans condition (même quand AI est désactivée — montre alors
``$0`` partout). 4 décimales pour garder visibles les montants
sub-centimes typiques d'un run d'enrichissement.

**Tests** :

- ``OpenRouterClient.complete()`` : un appel réussi avec
  ``generations.get_generation`` qui répond → ``usage_log`` contient un
  ``UsageRecord`` avec le bon ``cost_usd``/tokens.
- ``OpenRouterClient.complete()`` : le lookup ``/generation`` lève une
  exception → ``usage_log`` reste vide, ``complete()`` ne lève pas.
- ``stats_service`` : des lignes ``llm_usage_log`` à différents âges (30 min,
  3h, 12h, 30h) → ``stats.llm_cost.windows`` somme correctement pour
  1h/6h/24h ; table vide → toutes les fenêtres à ``0``.

**Acceptance criteria** :

- Le System panel affiche le coût OpenRouter cumulé sur 1h/6h/24h,
  rafraîchi à chaque chargement de ``/stats``.
- Le coût ne couvre que les appels d'enrichissement (pas la compaction admin).
- Un échec du lookup ``/generation`` n'interrompt jamais
  ``cron_enrich``/le refresh worker.
- Docs mises à jour : ``docs/DATA_MODEL.md`` (table ``llm_usage_log``),
  ``docs/API_SPEC.md`` (champ ``llm_cost`` dans ``/stats``).

---

## EPIC 11 — Filtres Explore

**Objectif** : Permettre à l'utilisateur de restreindre la vue Explore par score minimum et par source, via une barre de filtres permanente sous les tabs (2 lignes de chips scrollables).

> Dépend de EPIC 9 (Explore tab), EPIC 10-S4 (is_cold_start).

**Ordre de livraison** : `S1 → S2`. S1 est bloquant (les nouveaux query params sont requis pour que le frontend filtre côté serveur).

---

### Stories

#### [x] E11-S1 — Backend : query params de filtrage sur `/explore/*`

**Contexte** : Les endpoints `GET /explore/new` et `GET /explore/history` ne proposent aujourd'hui aucun filtrage. L'ajout de `min_score` et `source_ids` permet au frontend de déléguer le filtrage au serveur (pas de slicing côté client, pagination cohérente).

**Changements `GET /explore/new`** :

- Nouveau param `min_score` (float, 0.0 – 1.0, optionnel, défaut `0.0`) :
  - Condition SQL : `(ars.relevance_score >= :min_score OR ars.is_cold_start = TRUE)` — les articles cold passent toujours, cohérent avec E10-S4.
  - Valeur `0.0` explicite = même comportement qu'aujourd'hui (aucun filtrage).
- Nouveau param `source_ids` (liste de UUID, optionnel, max 20 valeurs) :
  - Encodé en query string répété : `?source_ids=uuid1&source_ids=uuid2`.
  - Condition SQL : `AND a.source_id IN (:source_ids)`.
  - Validation : chaque UUID fourni doit appartenir à `current_user` ; un UUID invalide ou étranger retourne `422` (pas de fuite silencieuse).
  - Liste vide ou param absent = pas de filtre.

**Changements `GET /explore/history`** :

- Mêmes params `min_score` et `source_ids`, mêmes règles de validation.
- `min_score` filtre sur `ars.relevance_score` (la colonne existe via le LEFT JOIN sur `article_relevance_scores`). Les articles sans score (edge case : article sans row `ars`) sont exclus quand `min_score > 0`.

**Pagination** : le curseur keyset ne change pas de format. Quand les filtres changent, le client recommence à la première page (cursor absent) — c'est lui qui en a la responsabilité.

**`GET /stats` — ajout `score_threshold`** :

Exposer le `SCORE_THRESHOLD` effectif (DB override via `SettingsService` puis env var) dans la réponse `/stats` :

```json
{
  "score_threshold": 0.6,
  "cron_fetch_interval_minutes": 15,
  ...
}
```

Cela permet au frontend d'afficher le chip "≥ seuil" avec la valeur réelle sans la hardcoder.

**Docs à mettre à jour** :
- `docs/API_SPEC.md` : params `min_score` et `source_ids` sur `GET /explore/new` et `GET /explore/history` ; champ `score_threshold` dans `GET /stats`.

**Tests** :
- `min_score=0.5` sur `/explore/new` exclut les articles avec score < 0.5, mais inclut les cold-start (is_cold_start=true).
- `source_ids=[uuid_A]` retourne uniquement les articles de la source A.
- `source_ids=[uuid_autre_user]` → 422.
- Combinaison `min_score + source_ids` : les deux filtres s'appliquent conjointement (AND).
- Pagination stable : deux pages successives avec mêmes filtres ne retournent pas de doublons.

**Acceptance criteria** :

- `GET /explore/new?min_score=0.75` n'inclut que les articles avec `relevance_score ≥ 0.75` ou `is_cold_start = true`.
- `GET /explore/new?source_ids=<uuid>` n'inclut que les articles issus de cette source.
- Un UUID de source appartenant à un autre utilisateur retourne `422`, pas un résultat filtré silencieusement.
- `GET /stats` inclut `score_threshold` (valeur effective, entre 0.0 et 1.0).
- Aucune régression sur les endpoints sans paramètres (défauts identiques à aujourd'hui).

---

#### [x] E11-S2 — Frontend : barre de filtres dans Explore

**Layout** :

```
┌─────────────────────────────────────┐
│  Explore                            │
│ ┌──────────┐  ┌─────────────┐       │
│ │ Nouveaux │  │ Lus         │       │
│ └──────────┘  └─────────────┘       │
│                                     │
│  Score :                            │
│  [0%] [≥25%] [≥50%] [≥60%✓] [≥75%] │  ← scrollable, seuil dynamique
│                                     │
│  Sources :                          │
│  [Le Monde✓] [HN✓] [BBC] …         │  ← scrollable, toutes sélectionnées
│ ─────────────────────────────────── │
│  Article 1                          │
│  Article 2                          │
└─────────────────────────────────────┘
```

**Chips Score** :

Valeurs fixes (dans cet ordre) :

| Chip       | `min_score` envoyé |
|------------|--------------------|
| 0%         | `0.0`              |
| ≥ 25 %     | `0.25`             |
| ≥ 50 %     | `0.50`             |
| ≥ 60 % (ou seuil) | valeur de `stats.score_threshold` |
| ≥ 75 %     | `0.75`             |

- Suppression du chip "Tous" — le chip avec la valeur du seuil serveur est sélectionné par défaut.
- Ajout du chip "0 %" pour inclure tous les articles (no filter).
- Le chip seuil affiche sa valeur numérique uniquement (ex. `≥ 60 %`) sans le label "seuil".
- Le chip seuil est masqué si `stats.score_threshold` est `0.0` ou non disponible.
- Un seul chip score actif à la fois (single-select).
- Par défaut : le chip correspondant à `score_threshold` est actif (ex. `≥ 60 %` si threshold=0.6).

**Chips Sources** :

- Suppression du chip "Toutes" — toutes les sources sont sélectionnées par défaut.
- Chargés via `GET /sources` au mount de l'écran (un seul fetch, réponse mise en cache dans un ref pour la durée de session).
- Les chips = noms des sources (tronqués à 18 chars avec ellipse si besoin).
- Multi-select : plusieurs sources peuvent être cochées simultanément (OR logique).
- Par défaut : **toutes les sources sont sélectionnées** (état `sourceIds: []` = all).
- Tapper un chip source le dé-sélectionne (il sort de la sélection).
- Ré-sélectionner toutes les sources revient à l'état `sourceIds: []`.
- Si l'utilisateur n'a qu'une seule source : la row Sources est masquée (inutile).

**Comportement** :

- Tout changement de filtre (score ou source) réinitialise le curseur et refetche la première page du tab actif.
- Les filtres sont **per-tab** : changer d'onglet (Nouveaux ↔ Lus) conserve les filtres de chaque onglet indépendamment.
- Pull-to-refresh (`BlobBackground.onRefresh`) remet les filtres à zéro ET refetche — comportement cohérent avec le `reload()` existant.
- Si `stats` n'est pas encore chargé au rendu initial, le chip "≥ seuil" n'est simplement pas affiché (pas de spinner dédié — la row Score s'affiche avec les autres chips).

**Empty state avec filtres actifs** :

Quand la liste est vide et qu'au moins un filtre non-défaut est actif :

> *"Aucun résultat avec ces filtres."*
> `[Réinitialiser les filtres]` → bouton inline qui réinitialise à "Tous" / "Toutes".

Le empty state existant (sans filtres) reste inchangé.

**État visuel d'un chip actif** :

- Background : `var(--accent-subtle)`
- Texte : `var(--accent)`
- Bordure : `1px solid var(--accent)` (pour distinguer du chip inactif qui n'a pas de bordure colorée)

**Docs à mettre à jour** :
- `docs/DESIGN_SYSTEM.md` : composant `FilterChip` (variantes active/inactive), pattern "filter bar à 2 rows" dans la section Explore.

**Acceptance criteria** :

- Les deux rows (Score et Sources) s'affichent sous les tabs Nouveaux / Lus.
- La row Sources est masquée si l'utilisateur n'a qu'une source.
- Tapper "≥ 50 %" envoie `?min_score=0.50` et recharge la liste depuis la première page.
- Le chip seuil affiche uniquement la valeur numérique (ex. "≥ 60 %"), sans label "seuil".
- Par défaut, le chip correspondant à `score_threshold` est actif (ex. "≥ 60 %" si seuil=0.6).
- Toutes les sources sont sélectionnées par défaut (état `sourceIds: []`).
- Tapper un chip source le dé-sélectionne ; aucun chip "Toutes" pour le re-sélectionner.
- Tapper plusieurs sources envoie `?source_ids=uuid1&source_ids=uuid2`.
- Les filtres de l'onglet "Nouveaux" ne sont pas réinitialisés quand on bascule sur "Lus" et inversement.
- Pull-to-refresh remet le score au chip seuil et sélectionne toutes les sources avant de recharger.
- Le empty state avec filtres actifs propose un bouton "Réinitialiser les filtres".
- `npm run build` passe sans erreur TypeScript.

---

#### [x] E11-S3 — Frontend : geste swipe vertical au-delà des limites de défilement

**Problème** : Sur les articles longs, l'utilisateur peut scroller le contenu de l'article, mais le swipe vertical ne fonctionne pas fiablement pour passer à l'article suivant — seul le bouton "Article suivant" au bas du slide fonctionne.

**Solution** : Ajouter un détecteur de geste tactile qui, en haut et bas du défilement intérieur de l'article, interprète un swipe vertical comme une commande de navigation vers l'article suivant/précédent.

**Implémentation** (`pwa/src/components/FeedArticleSlide.tsx`) :

- Ajouter des handlers `onTouchStart` et `onTouchEnd` au conteneur `.slide-scroll`.
- Sur `touchstart` : enregistrer la position Y, le timestamp, et l'état du scroll (atTop, atBottom).
- Sur `touchend` : calculer le delta Y et déterminer si c'est un swipe :
  - Seuil distance : ≥ 40 px.
  - Seuil vitesse : ≥ 0.1 px/ms.
  - Si le delta répond à l'un des deux, c'est un swipe.
- Actions :
  - **Swipe vers le bas (dy > 0) au-dessus du slide** (`atTop`) → snapper au slide **précédent** via `scrollIntoView`.
  - **Swipe vers le haut (dy < 0) au-bas du slide** (`atBottom`) → snapper au slide **suivant**.
  - **Cas particulier** : article court où `atTop && atBottom` → swipe haut = suivant.
- Comportement : utiliser `scrollIntoView({ behavior: 'smooth', block: 'start' })` pour un snap fluide.

**Acceptance criteria** :

- Sur un article dont la scroll-height dépasse la viewport, un swipe vers le haut au bas du contenu scrollable passe à l'article suivant.
- Sur un article court (pas de scroll possible), un swipe vers le haut passe au suivant.
- Un swipe vers le bas au-dessus de l'article passe au précédent (s'il existe).
- Les swipes accidentels (petite distance, lent) n'activent pas la navigation.
- La navigation par swipe ne se déclenche que si on est réellement à la limite (top ou bottom) du défilement intérieur.
- Aucune régression sur le défilement normal à l'intérieur de l'article.

---

#### [x] E11-S4 — Frontend : conserver filtres + scroll au retour d'un article

**Problème** : Taper un article depuis Explore navigue vers le Feed
(`/?start=<id>`), ce qui **démonte** `Explore.tsx`. Au retour (tab Explore ou
bouton retour), le composant se remonte à zéro : onglet `Nouveaux`, filtres
par défaut, scroll en haut. L'utilisateur perd le contexte de navigation qu'il
avait construit (filtres actifs + position dans la liste).

**Solution** : Un snapshot persisté en `sessionStorage` capture l'état au
démontage et le restaure au remontage — sans refetch, donc les rows déjà
chargées et la position de scroll sont conservées. `sessionStorage` (et non
une variable module) car sur mobile le geste retour déclenche souvent un
**rechargement complet** de `/explore` plutôt qu'un popstate SPA, ce qui
effacerait tout état en mémoire. L'écriture a lieu au démontage SPA fiable
(Explore → article), donc la restauration marche aussi bien via popstate que
via reload.

**Implémentation** (`pwa/src/screens/Explore.tsx`) :

- `sessionStorage` clé `niouzou_explore_snapshot` → `{ owner, mode, tabs,
  scrollTop }`, via helpers `readSnapshot()` / `writeSnapshot()`.
- États `mode` / `tabs` initialisés en lazy depuis le snapshot (`useState(() =>
  restorableSnapshot()?.… )`).
- `scrollRef` sur le conteneur scrollable. Un `useLayoutEffect([])` restaure
  `scrollTop` au montage (avant paint, donc pas de saut visible) et écrit le
  snapshot dans son cleanup de démontage. Le dernier `{ mode, tabs }` est tenu
  dans un ref (`latest`) mis à jour via un `useEffect` passif pour rester
  lisible depuis le cleanup sans relancer l'effet.
- **Isolation par utilisateur** : `owner = tokens.email()`. Le logout ne
  recharge pas la page, donc sans cette clé un second utilisateur verrait les
  rows du précédent. `restorableSnapshot()` renvoie `null` si l'owner ne
  correspond pas à l'email courant.
- Le pull-to-refresh continue de réinitialiser les onglets ; le snapshot
  reflètera l'état rafraîchi au prochain démontage.

**Acceptance criteria** :

- Depuis Explore, scroller, activer des filtres (score / sources), ouvrir un
  article, puis revenir → onglet, filtres et position de scroll sont restaurés.
- La liste n'est pas refetchée au retour (pas de spinner, pas de re-tri).
- Le pull-to-refresh réinitialise bien filtres + scroll.
- Le retour fonctionne **que le geste retour soit un popstate SPA ou un
  rechargement complet** de `/explore` (cas fréquent sur mobile).
- Après logout puis login d'un autre utilisateur dans le même onglet, Explore
  repart propre (pas de fuite des rows/filtres de l'utilisateur précédent).
- La fermeture de l'onglet vide le snapshot (`sessionStorage`).

---

## EPIC 12 — Robustesse des keywords ⛔ REMPLACÉE PAR EPIC 16

> **Statut (2026-06-10) : abandonnée avant implémentation, remplacée par EPIC 16 (Smart Match).**
> Audit : la taxonomie fixe (~200 termes) fait s'effondrer le pouvoir discriminant du scoring
> (tous les articles d'un même domaine portent le même sac de keywords) et **aggrave** le cas
> multi-intérêts via les termes parapluie partagés entre clusters (`sport`, `tech`, `france`).
> S3 contenait en outre une erreur de spec bloquante : `xx_ent_wiki_sm` n'émet ni `GPE` ni
> `PRODUCT` (labels WikiNER : `LOC`, `MISC`, `ORG`, `PER`) — ses tests d'acceptance étaient
> infaisables. La canonicalisation du vocabulaire survit en E16-S6 ; le `kind`/badges (S1/S4)
> sont abandonnés avec la taxonomie. Le texte original est conservé ci-dessous pour référence.

**Objectif** : Remplacer l'extraction libre de keywords (TF-IDF brut / LLM non contraint) par une extraction à deux niveaux stables — une taxonomie fixe de ~200 topics et des entités nommées dynamiques via NER. Résultat : des `keyword_weights` qui s'accumulent de façon cohérente sur des termes récurrents, et non sur des tokens éphémères propres à un seul article.

> Dépend de EPIC 5 (enrichissement AI/TF-IDF), EPIC 9 (refonte keyword_weights).

**Problèmes actuels résolus** :
- TF-IDF extrait des termes rares propres à un seul article → n'accumulent jamais de poids utiles
- LLM libre génère des variantes ("IA", "intelligence artificielle", "AI", "LLM") → poids fragmentés entre synonymes
- Aucune distinction entre topics stables (rugby) et entités spécifiques (Toulouse, Ntamack)

---

### Deux niveaux de keywords

| Niveau | `kind` | Source | Vocabulaire | Stabilité |
|---|---|---|---|---|
| **Taxonomie** | `taxonomy` | Liste hardcodée ~200 termes | Fixe | Permanente — change uniquement par PR |
| **Entités** | `entity` | NER spaCy (ORG, GPE, PER, PRODUCT) | Illimité | Croît au fil des articles |
| *(legacy)* | `legacy` | Ancien TF-IDF/LLM libre | Variable | Marqueur de migration uniquement |

Les deux niveaux alimentent la même table `keyword_weights` avec la même formule. Pas de pondération différentielle entre kinds.

**Ordre de livraison** : S1 → S2 → S3 → S4. S1 est bloquant.

---

### Stories

#### [ ] E12-S1 — Schéma : colonne `kind` sur `article_keywords`

Migration Alembic : ajouter `kind VARCHAR NOT NULL DEFAULT 'legacy'` sur `article_keywords`.

Valeurs : `'taxonomy'` | `'entity'` | `'legacy'`.

Mettre à jour le modèle SQLAlchemy `ArticleKeyword` et le schéma Pydantic `ArticleKeywordOut`.

**Acceptance criteria** :
- Migration tourne proprement sur DB vierge et DB avec données existantes
- Les rows existantes ont `kind='legacy'` après migration
- Les nouveaux keywords insérés par `cron_enrich` ont `kind='taxonomy'` ou `kind='entity'`

---

#### [ ] E12-S2 — Taxonomie fixe (~200 termes)

**Fichier** : `api/niouzou/data/taxonomy.py`

Structure : dict par domaine → liste de termes canoniques minuscules. Un flat `set` dérivé pour les lookups O(1).

```python
TAXONOMY: dict[str, list[str]] = {
    "sport":        ["sport", "rugby", "football", "tennis", "cyclisme",
                     "natation", "athletisme", "basketball", "handball",
                     "ski", "formule-1", "judo", "golf", "voile",
                     "top-14", "pro-d2", "six-nations", "ligue-des-champions"],
    "tech":         ["tech", "intelligence-artificielle", "machine-learning",
                     "open-source", "linux", "python", "javascript",
                     "cybersecurite", "cloud", "devops", "startup",
                     "blockchain", "crypto", "web", "mobile"],
    "politique":    ["politique", "france", "europe", "etats-unis",
                     "elections", "parlement", "gouvernement", "diplomatie",
                     "guerre", "conflit", "terrorisme", "defense"],
    "economie":     ["economie", "finance", "bourse", "immobilier",
                     "inflation", "emploi", "fusions-acquisitions"],
    "sante":        ["sante", "medecine", "cancer", "vaccin", "medicament",
                     "recherche-medicale", "nutrition", "psychologie"],
    "environnement":["environnement", "climat", "energie", "nucleaire",
                     "renouvelable", "ecologie", "biodiversite"],
    "science":      ["science", "astronomie", "physique", "biologie",
                     "genetique", "espace", "recherche"],
    "culture":      ["culture", "cinema", "musique", "litterature",
                     "art", "jeux-video", "streaming", "medias"],
    "societe":      ["societe", "education", "immigration", "justice",
                     "police", "religion", "droits-humains"],
    "international":["international", "proche-orient", "afrique", "asie",
                     "amerique-latine", "ukraine"],
}

TAXONOMY_TERMS: frozenset[str] = frozenset(
    t for terms in TAXONOMY.values() for t in terms
)
```

> La liste ci-dessus est un point de départ (~140 termes). L'objectif cible est ~200 termes ; les manquants sont ajoutés par PR avant de merger E12-S2.

**Prompt LLM modifié** (`services/enrichment_service.py`) :
- Injecter `sorted(TAXONOMY_TERMS)` dans le system prompt
- Consigne : *"Extrait uniquement des keywords présents dans cette liste. Retourne entre 3 et 8 termes avec leur salience (0.0–1.0). Ignore tout terme hors-liste."*
- Format de réponse inchangé : `[{"term": "rugby", "salience": 0.9}, ...]`
- Les termes retournés hors-taxonomie sont filtrés côté Python sans lever d'erreur

**Fallback TF-IDF modifié** :
- Conserver l'extraction TF-IDF existante
- Post-filtrer : ne garder que les termes présents dans `TAXONOMY_TERMS`
- Salience : score TF-IDF normalisé 0.0–1.0 sur les termes retenus uniquement

**Stockage** : `kind='taxonomy'` sur les rows insérées.

**Tests** :
- LLM retourne `"dupont"` → ignoré, non inséré
- LLM retourne `"rugby"` → inséré avec `kind='taxonomy'`, salience retournée
- TF-IDF sur article tech → extrait `"open-source"`, `"python"` si présents dans `TAXONOMY_TERMS`
- Article hors-taxonomie → 0 keywords taxonomy, pas d'erreur, enrichissement continue vers NER

**Acceptance criteria** :
- Aucun keyword `kind='taxonomy'` contient un terme absent de `TAXONOMY_TERMS`
- Au moins 1 keyword taxonomy par article enrichi (sauf contenu < 50 mots)
- `MAX_KEYWORDS_PER_ARTICLE` s'applique sur les taxonomy keywords indépendamment des entity keywords

---

#### [ ] E12-S3 — Entités nommées (NER spaCy)

**Dépendance** : `spacy` + modèle `xx_ent_wiki_sm` (multilingual, ~12 MB). Ajouté dans `api/pyproject.toml`.

**Nouveau composant** : `api/niouzou/enrichment/ner_extractor.py`

```python
class NERExtractor:
    _nlp = None  # chargé une fois, singleton de module

    def extract(self, text: str, title: str) -> list[dict]:
        """
        Retourne [{"term": "toulouse", "salience": 0.7, "kind": "entity"}, ...]
        """
```

**Labels retenus** : `ORG`, `GPE`, `PER`, `PRODUCT`

**Normalisation** :
- `.lower().strip()`
- Suppression de la ponctuation en début/fin
- Déduplication : occurrences multiples du même terme fusionnées

**Salience formula** :
```
raw = count_in_text / max(1, total_entity_mentions)
boost = 1.5 if term appears in title else 1.0
salience = min(0.9, raw * boost)  # floor à 0.1 si count >= 1
```

**Filtres** :
- Rejeter les termes < 3 caractères
- Rejeter les termes présents dans `TAXONOMY_TERMS` (évite les doublons — taxonomy prime)
- Limite : `MAX_ENTITY_KEYWORDS_PER_ARTICLE` (défaut : `10`, nouveau paramètre `app_settings`)

**Intégration dans `cron_enrich`** :
- NER tourne sur `article.content` si disponible, sinon `article.title + " " + article.summary_short`
- S'exécute après l'extraction taxonomy (taxonomy prime en cas de conflit de terme)
- Les deux types sont insérés dans la même transaction `article_keywords`

**Tests** :
- `"Toulouse gagne le Top 14"` → entité `("toulouse", GPE/ORG)`
- Article Python → entités `("python", PRODUCT)`, `("linux", PRODUCT)`
- `"rugby"` présent dans le texte comme entité → non inséré en `entity` (déjà couvert par taxonomy)
- Texte vide → liste vide, pas d'exception
- Modèle chargé une seule fois au démarrage du worker (pas de rechargement à chaque article)

**Acceptance criteria** :
- Chaque article enrichi contient des keywords `kind='entity'` (sauf contenu < 50 mots)
- Aucun terme taxonomy n'apparaît aussi en `kind='entity'` pour le même article
- `MAX_ENTITY_KEYWORDS_PER_ARTICLE` respecté
- Temps d'enrichissement NER < 200 ms par article sur CPU

---

#### [ ] E12-S4 — UI : badges `kind` dans Keywords screen

**Contexte** : l'utilisateur ne sait pas d'où vient un keyword. Afficher l'origine aide à comprendre pourquoi un terme est apparu et pourquoi il accumule (ou non) du poids.

**Changement API** (`GET /keywords`) : ajouter `kind: 'taxonomy' | 'entity' | 'legacy'` dans `KeywordWeightOut`.

La valeur est dérivée des `article_keywords` associés : si le keyword a au moins un row `kind='taxonomy'` → `'taxonomy'`, sinon si au moins un `kind='entity'` → `'entity'`, sinon `'legacy'`.

**Changement PWA** (`screens/Keywords.tsx`) :
- Badge compact à droite du terme : "topic" (pill cyan) pour taxonomy, "entité" (pill gris) pour entity, aucun badge pour legacy
- Pas de filtre ni de section séparée — juste information visuelle

**Acceptance criteria** :
- Keywords taxonomy affichent le badge "topic"
- Keywords entity affichent le badge "entité"
- Keywords legacy n'ont aucun badge
- `npm run build` passe sans erreur TypeScript

---

### Notes d'implémentation

**Pas de ré-enrichissement massif** : les articles existants gardent leurs keywords `kind='legacy'`. Ils décroissent naturellement dans `keyword_weights` au fur et à mesure que les nouveaux articles accumulant de vrais poids taxonomy/entity prennent le relais. Un reset admin optionnel (passer tous les articles `enriched` → `pending`) est hors scope de cette epic.

**Interaction avec keyword compaction** (E10-S3) : la compaction continue de fonctionner sur tous les kinds. Elle est particulièrement utile pour les entités (ex: `"stade toulousain"` → `"toulouse"`). Les entités `kind='entity'` bénéficient donc de la compaction sans changement.

**`keyword_weights` inchangée** : même table, même formule de poids. Les deux kinds y contribuent à égalité.

---

## EPIC 13 — Polish admin & sources (juin 2026)

**Objectif** : nettoyer quelques rugosités UX (placement badge AI, toggle peu utile sur Sources) et donner à l'admin de vrais leviers (édition des prompts LLM, suppression d'un user, gestion des sources via toggle ON/OFF).

### Stories

- [x] **E13-S1** — Badge "AI Summary" dans le cadre du résumé IA
- [x] **E13-S2** — Prompts LLM stockés en DB et éditables depuis l'admin
- [x] **E13-S3** — Suppression hard d'un user (cascade)
- [x] **E13-S4** — Retirer le toggle "Fetch full content" de Sources UI
- [x] **E13-S5** — Toggle ON/OFF par source + hard delete caché

---

#### [x] E13-S1 — Badge "AI Summary" dans le cadre du résumé IA

**Contexte.** `pwa/src/components/FeedArticleSlide.tsx:323-364` affiche deux blocs : (a) l'**executive summary** (bullets, le vrai résumé IA, encadré) et (b) le **short summary** (fallback, sans cadre). Le sparkles ✨ est actuellement collé au label "Summary" du short summary — visuellement détaché et associé au mauvais bloc.

**Acceptance.**
- Le cadre de l'executive summary affiche en haut à gauche un badge `✨ AI Summary` (sparkles + label, couleur accent du design system).
- Le sparkles est retiré du label "Summary" du short summary, qui redevient un label neutre.
- Pas de cadre ajouté au short summary — il reste un paragraphe simple sous le bloc IA.

**Files.** `pwa/src/components/FeedArticleSlide.tsx`.

---

#### [x] E13-S2 — Prompts LLM stockés en DB et éditables depuis l'admin

**Contexte.** Les prompts (summary court, executive summary, keywords) sont hardcodés dans `api/niouzou/services/enrichment_service.py` et `openrouter_client.py`. Pour itérer dessus sans redéploiement, on les déplace en DB. **La DB devient la seule source de vérité** — pas de fallback hardcodé après migration.

**Modèle** — nouvelle table `llm_prompts` :
- `name` (PK, ex. `enrichment.summary_short`, `enrichment.summary_executive`, `enrichment.keywords`)
- `body` (Text, le prompt brut avec placeholders type `{title}`, `{content}`)
- `updated_at`

**Migration Alembic.** Crée la table + INSERT des prompts actuellement hardcodés (un row par prompt). **Le prompt `enrichment.summary_short` est remplacé par une version plus longue** (~3–4 phrases vs 1–2 actuellement) à valider à la rédaction de la migration.

**Backend.**
- `services/llm_prompts_service.py` : `get(name) -> str`, `list() -> [(name, body, updated_at)]`, `update(name, body)`. Cache en mémoire avec TTL court (~30s) pour éviter un hit DB par enrichissement.
- `enrichment_service.py` et `openrouter_client.py` : remplacement des f-strings hardcodés par `await prompts.get("…")` + `.format(...)` pour les placeholders.
- Suppression des constantes Python de prompts (DB = source de vérité).

**API.**
- `GET /admin/prompts` → `[{name, body, updated_at}]`
- `PATCH /admin/prompts/{name}` body `{body: str}` → renvoie la row mise à jour. Guard `CurrentAdmin`.

**UI (`pwa/src/screens/Admin.tsx`).** Nouvelle section "LLM Prompts" :
- Une carte par prompt avec : `name` en titre, `<textarea>` monospace pleine largeur (~12 lignes, redimensionnable), bouton "Save" + bouton "Copy". Pas de formatage Markdown, pas de syntax highlight — texte brut.
- Save désactivé tant qu'aucune modif n'est en attente.

**Files.** `api/niouzou/models/llm_prompt.py` (new), `api/niouzou/migrations/versions/XXXX_llm_prompts.py` (new), `api/niouzou/services/llm_prompts_service.py` (new), `api/niouzou/routers/admin.py`, `api/niouzou/schemas/admin.py`, `api/niouzou/services/enrichment_service.py`, `api/niouzou/services/openrouter_client.py`, `pwa/src/api/admin.ts`, `pwa/src/screens/Admin.tsx`.

---

#### [x] E13-S3 — Suppression hard d'un user (cascade)

**Contexte.** Aucun moyen actuel de supprimer un user pour de vrai. Demande RGPD + ménage souhaités.

**Backend.**
- Vérifier/ajouter `ondelete="CASCADE"` sur toutes les FK pointant vers `users.id` : `sources.user_id`, `article_feedback.user_id`, `article_impressions.user_id`, `article_relevance_scores.user_id`, `keyword_weights.user_id`, `saved_articles.user_id`. Migration Alembic pour les FK qui n'ont pas déjà le cascade.
- **Articles** : pendent de `Source` → cascade automatique via `sources` quand on cascade `users`. Les `article_keywords` doivent aussi cascader depuis `articles` (à vérifier).
- `DELETE /admin/users/{id}` (guard `CurrentAdmin`) :
  - 400 si `id == current_user.id` (un admin ne se supprime pas lui-même)
  - 404 si user inconnu
  - Sinon `session.delete(user)` + commit → FastAPI 204.
- **Pas de coupure côté Miniflux** : les feeds Miniflux ne sont pas par-user (ils sont globaux côté Miniflux). On laisse les feeds Miniflux en place.

**UI (`pwa/src/screens/Admin.tsx`).** Sur chaque ligne user, bouton "Delete" (rouge) → modale "Tape l'email du user pour confirmer" → input texte qui doit matcher exactement → bouton "Delete forever" activé seulement si match.

**Files.** `api/niouzou/migrations/versions/XXXX_cascade_user_delete.py` (new), `api/niouzou/routers/admin.py`, `api/niouzou/schemas/admin.py`, `pwa/src/api/admin.ts`, `pwa/src/screens/Admin.tsx`.

---

#### [x] E13-S4 — Retirer le toggle "Fetch full content" de Sources

**Contexte.** `pwa/src/screens/Sources.tsx:287` expose un toggle "fetch_full_content" qui n'apporte plus de valeur côté UX (et complexifie l'écran).

**Acceptance.**
- Retrait du toggle et de tout le markup associé dans `Sources.tsx`.
- Retrait du handler `handleToggleFullContent`.
- **Backend conservé** : champ `fetch_full_content` reste en DB, l'appel `miniflux.update_feed(crawler=True)` reste dans `sources_service.add_source` avec la valeur par défaut actuelle. Endpoint `PATCH /sources/{id}` reste capable de toggle ce champ pour usage admin futur, mais l'UI ne l'expose plus.

**Files.** `pwa/src/screens/Sources.tsx`.

---

#### [x] E13-S5 — Toggle ON/OFF par source + hard delete caché

**Contexte.** La poubelle actuelle déclenche un soft delete (`sources_service.delete_source`) — le user pense supprimer pour de vrai alors que le flux et les articles restent vivants. UX trompeuse.

**Sémantique.**
- **ON (actif)** : comportement actuel — fetch des nouveaux articles, articles visibles dans Feed/Explore.
- **OFF (en pause)** : plus de fetch (cron skip déjà sur `deleted_at IS NOT NULL`), articles existants **masqués** du Feed et de l'Explore (filtre déjà en place sur `Source.deleted_at.is_(None)`).
- Toggler ON → OFF : `deleted_at = now()`. OFF → ON : `deleted_at = NULL`.
- **Hard delete caché** : voie séparée pour réellement supprimer la source + ses articles + ses dépendances (feedback, impressions, scores, article_keywords). Pas exposé dans l'UI standard — disponible via API (et éventuellement un menu caché plus tard).

**Backend.**
- `services/sources_service.py` : nouvelle méthode `set_source_active(user_id, source_id, active: bool)`. La méthode `delete_source` actuelle est renommée `hard_delete_source` et fait un vrai `session.delete(source)` (cascade vers articles & dépendances via FK CASCADE).
- Migration Alembic : ajouter `ondelete="CASCADE"` sur `articles.source_id`, `article_feedback.article_id`, `article_impressions.article_id`, `article_relevance_scores.article_id`, `article_keywords.article_id` si pas déjà en place.
- Routes :
  - `PATCH /sources/{id}` : accepter `{active: bool}` en plus de l'existant. Active = mappé sur `deleted_at`.
  - `DELETE /sources/{id}` : passe en mode toggle off par défaut. Query param `?hard=true` → hard delete réel.

**UI (`pwa/src/screens/Sources.tsx`).**
- Remplacement de l'icône poubelle par un `Switch` "Active" (style proche du toggle full-content actuel — réutilisable au moment du retrait en S4).
- Sources OFF : opacité réduite (0.5) sur la ligne pour signaler la pause.
- Pas de bouton "Delete forever" dans l'UI (caché).

**Files.** `api/niouzou/services/sources_service.py`, `api/niouzou/schemas/sources.py`, `api/niouzou/routers/sources.py`, `api/niouzou/migrations/versions/XXXX_cascade_source_delete.py` (new si nécessaire), `pwa/src/api/sources.ts`, `pwa/src/screens/Sources.tsx`.

---

### Notes E13

**Ordre d'attaque** : S4 (UI trim) → S1 (UI pure) → S5 (toggle sources + cascade) → S3 (delete user, réutilise les patterns cascade de S5) → S2 (prompts en DB, le plus gros).

**Tests** : pas de gros besoin de tests automatisés pour S1/S4 (UI cosmétique). S2/S3/S5 doivent tester le chemin DB (cascade effective + endpoints admin).

---

## EPIC 14 — Synchronisation Niouzou ↔ Miniflux sur le cycle de vie des sources (juin 2026)

**Objectif** : rendre la feature pause/hard-delete des sources (E13-S5) *réellement* utilisable en bout de chaîne. Aujourd'hui, mettre une source OFF côté Niouzou ne touche pas Miniflux : le flux continue d'être pollé, ses entrées non lues s'empilent, et comme `cron_fetch` ne marque comme lues que les entrées **matched**, les orphelines saturent oldest-first le fenêtre de fetch (`limit=100, order=asc`) jusqu'à bloquer complètement le pipeline d'ingestion.

**Régression observée en prod (2026-06-07)** : la source "Rugby" pausée le 2026-05-30 a accumulé 119 unread côté Miniflux. À partir du 2026-06-07 22:00 UTC, les 100 plus anciennes unread retournées par Miniflux étaient toutes du feed orphelin → 0 match → 0 entrée nouvellement ingérée pendant >24 h, alors que les autres flux continuaient à publier.

**Principe.** Deux couches indépendantes, chacune utile sans l'autre :

1. **Couche métier** — la transition d'état d'une source (`pause`, `resume`, `hard-delete`) propage sa conséquence à Miniflux quand plus aucun user actif ne référence le feed.
2. **Couche défensive** — `cron_fetch` traite *toujours* les entrées venant d'un feed orphelin (matched aucun source actif) comme du bruit à marquer lu, sans jamais les insérer en DB ni déclencher d'enrichment.

La couche 2 est un garde-fou : elle protège du cas où Miniflux est manipulé hors-Niouzou (UI Miniflux, panne réseau pendant la sync, divergence historique). C'est elle qui débloquera la prod naturellement au prochain tick après déploiement — pas de script manuel.

### Stories

- [x] **E14-S1** — `cron_fetch` marque les unmatched comme lues (garde-fou)
- [x] **E14-S2** — Pause/resume/hard-delete d'une source propage à Miniflux

---

#### [x] E14-S1 — `cron_fetch` marque les unmatched comme lues (garde-fou)

**Contexte.** `api/niouzou/crons/fetch.py:121` ne marque comme lu que `handled_ids` (les entrées qui ont matché une source active). Une entrée venant d'un feed orphelin (feed Miniflux référencé par aucune source active Niouzou) reste donc unread indéfiniment et revient à chaque tick puisque l'API Miniflux est appelée avec `offset=0&order=asc`. Au bout d'un certain nombre d'unread orphelines, les 100 plus anciennes sont toutes orphelines → fetch bloqué.

**Sémantique.** Toute entrée Miniflux qui n'a pas de source active correspondante (qu'elle soit pausée ou jamais créée côté Niouzou) est du bruit du point de vue Niouzou. Elle ne doit jamais entrer en DB, jamais être enrichie (pas de tokens LLM gâchés), et doit être marquée lue côté Miniflux pour ne plus polluer la fenêtre de fetch.

**Acceptance.**
- Après un fetch, les entrées **matched** ET **unmatched** sont marquées lues dans Miniflux par un seul `PUT /v1/entries` qui réunit les deux listes.
- Le `mark_entries_read` reste appelé **après** le commit DB des matched (préservation du comportement crash-safe actuel).
- `articles_fetched` retourné par `cron_fetch.run()` continue de refléter uniquement les entrées **ingérées** (matched), pas les unmatched. La métrique `pipeline_runs.articles_fetched` garde sa sémantique actuelle.
- Logging : compter et logger séparément `marked_matched` et `marked_unmatched` pour pouvoir détecter une dérive Niouzou/Miniflux dans les logs (`cron_fetch: marked X matched + Y unmatched as read in Miniflux`).
- Aucun enrichment n'est déclenché pour une unmatched (par construction : elles ne sont jamais insérées comme `Article`).

**Edge cases.**
- Si la couche métier E14-S2 manque une étape de sync (ex. exception Miniflux pendant un pause), E14-S1 nettoie au tick suivant : pas de pile d'unread qui se reforme.
- Si un admin remet ON une source pausée pendant que des entrées sont encore en fly côté Miniflux, certaines auront été marquées lues par E14-S1 et seront perdues pour Niouzou. Tradeoff accepté : la pause est censée vouloir dire "je ne veux plus rien de ce flux pour le moment".

**Files.** `api/niouzou/crons/fetch.py`, `api/tests/test_cron_fetch.py`.

**Tests.**
- `cron_fetch` ingère N matched et 0 unmatched : `mark_entries_read` est appelé avec N ids, comportement identique à aujourd'hui.
- `cron_fetch` reçoit M unmatched seulement (aucune source ne matche) : aucune insertion dans `articles`, `mark_entries_read` appelé avec M ids, retour `0`.
- Cas mixte : N matched + M unmatched → `mark_entries_read` reçoit N+M ids, `articles` gagne N rows.
- Régression : si le commit DB des matched échoue, on **ne** marque PAS les unmatched non plus (sinon on perdrait du contenu valide en cas de crash partiel). Ordre : commit DB matched → mark_read(matched ∪ unmatched).

---

#### [x] E14-S2 — Pause/resume/hard-delete d'une source propage à Miniflux

**Contexte.** `sources_service.deactivate_source` / `update_source(active=False)` / `hard_delete_source` modifient l'état Niouzou sans toucher Miniflux. Un feed Miniflux pouvant être partagé entre plusieurs users (cas multi-user, cf. `_register_in_miniflux` qui réutilise un feed existant), on ne peut pas désactiver/supprimer aveuglément côté Miniflux : il faut compter les sources actives restantes.

**Sémantique.**

| Transition Niouzou | Côté Miniflux si plus aucune source active ne référence le feed | Sinon |
|---|---|---|
| Pause (`active=true → false`) | `PUT /v1/feeds/{id}` avec `disabled: true` | aucun changement |
| Resume (`active=false → true`) | `PUT /v1/feeds/{id}` avec `disabled: false` (idempotent : déjà enabled = no-op) | aucun changement |
| Hard delete | `DELETE /v1/feeds/{id}` (purge le feed + ses entrées Miniflux) | aucun changement |

"Source active" = `sources.deleted_at IS NULL` (cohérent avec le filtre `cron_fetch` et `ranked_query`).

**Pourquoi `disabled` plutôt que `DELETE` pour la pause ?** Le user peut vouloir reprendre. `disabled` arrête le polling Miniflux sans perdre l'historique des unread déjà fetched (ils seront balayés par E14-S1) ni l'identifiant `feed_id`. La reprise est un simple `disabled: false`.

**Backend.**

- `MinifluxClient` (`api/niouzou/services/miniflux_client.py`) : étendre `update_feed` pour accepter `disabled: bool | None` (kwarg optionnel, ne change rien si non passé). Ajouter `delete_feed(feed_id: int) -> None` qui fait `DELETE /v1/feeds/{id}` (Miniflux renvoie 204).
- `SourcesService` (`api/niouzou/services/sources_service.py`) :
  - Nouvelle méthode privée `_count_active_subscribers(feed_id: int, exclude_source_id: uuid.UUID | None) -> int` qui compte les `sources` actives référençant `miniflux_feed_id`, avec exclusion optionnelle de la source en cours de transition.
  - `deactivate_source` et `update_source(active=False)` : après avoir mis `deleted_at`, si `_count_active_subscribers(feed_id, exclude=source.id) == 0` → `miniflux.update_feed(feed_id, disabled=True)`. Échec Miniflux → log WARNING, **on ne fail pas la transition Niouzou** (le state Niouzou est la source de vérité ; E14-S1 nettoie le reste).
  - `update_source(active=True)` : si la source était auparavant pausée et est la **première** à redevenir active sur ce feed → `miniflux.update_feed(feed_id, disabled=False)`. Idem : log WARNING en cas d'échec, pas de fail.
  - `hard_delete_source` : après le `session.delete(source)` (mais dans la même transaction, donc la source est déjà "removed" du count), si `_count_active_subscribers(feed_id, exclude=None) == 0` ET `_count_inactive_subscribers(feed_id) == 0` → `miniflux.delete_feed(feed_id)`. Sinon on laisse le feed Miniflux en place pour les autres users.
- Pas de changement de schéma DB, pas de migration.

**API.** Aucun changement de contrat. Les routes `PATCH /sources/{id}`, `DELETE /sources/{id}` gardent leur signature ; seul leur effet de bord côté Miniflux change.

**Note importante** : si le compteur revient `> 0` (un autre user actif partage le feed), aucun appel Miniflux n'est fait. C'est ce qui rend la feature safe en multi-user.

**Files.** `api/niouzou/services/miniflux_client.py`, `api/niouzou/services/sources_service.py`, `api/tests/test_sources_service.py`.

**Tests** (avec mock Miniflux via respx, pattern existant) :
- Pause d'une source qui était la seule active sur son feed → `PUT /v1/feeds/{id}` avec `disabled: true` est appelé.
- Pause d'une source partagée avec un autre user actif → aucun appel Miniflux.
- Resume d'une source quand elle était la seule pausée (toutes les autres étaient déjà actives) → aucun appel Miniflux (idempotent côté state Niouzou, le feed Miniflux était déjà enabled).
- Resume d'une source quand elle était la seule sur son feed et que le feed est disabled → `PUT /v1/feeds/{id}` avec `disabled: false`.
- Hard delete d'une source qui était la seule (active ou pausée) sur son feed → `DELETE /v1/feeds/{id}`.
- Hard delete d'une source partagée → aucun appel Miniflux.
- Échec Miniflux pendant la propagation (HTTP 500 mocké) → la transition Niouzou aboutit quand même, un WARNING est loggé.

---

### Notes E14

**Ordre d'attaque** : S1 d'abord (débloque la prod au prochain tick après déploiement, sans manipuler Miniflux à la main). Puis S2 (évite que ça se reproduise et économise des ressources Miniflux/réseau pour les flux pausés).

**Débug naturel de la prod** : une fois E14-S1 mergé et déployé, le prochain tick `cron_fetch` mark-as-read les ~100 entrées rugby orphelines. Le tick suivant nettoie les ~19 restantes. Au troisième tick (~45 min après deploy), Miniflux retourne des entrées matched des autres flux → ingestion + enrichment reprennent. Aucune intervention humaine requise — c'est ce qui rend E14-S1 testable de bout en bout en prod.

**E14-S2 sans E14-S1** serait insuffisant : il y a déjà ~119 unread rugby orphelines en prod ; sans S1, elles resteraient bloquantes même si on patche le code de pause. À l'inverse, E14-S1 sans E14-S2 fonctionne mais gaspille du polling Miniflux sur les flux pausés ad vitam.

**Pas de changement à `/admin` ni à `Stats`** dans cette epic. Le panneau distinct_keyword_count (global) reste tel quel — sujet séparé.

---

## EPIC 15 — Dédup des articles à l'ingestion (juin 2026)

**Objectif** : éviter qu'un user abonné à deux flux RSS qui republient le même article (typiquement "Le Monde" et "Le Monde Sciences", ou un agrégateur thématique qui réutilise les URLs d'un flux principal) se retrouve avec le même article ingéré N fois dans Niouzou.

**Constat prod (2026-06-08)** : le user `9f8ca23f-…` abonné à "Le Monde.fr" (feed_id=1) ET "Sciences : Toute l'actualité sur Le Monde.fr." (feed_id=5) accumule des doublons exacts d'URL pour chaque article publié sur les deux flux — environ une quinzaine identifiés. Côté Miniflux, chaque flux a son propre `entry_id` pour la même URL, donc la contrainte unique actuelle `(source_id, miniflux_entry_id)` ne déclenche pas. Conséquences :

- Le feed affiche deux cartes pour le même contenu.
- Le filtre d'impression (`ai.article_id IS NULL`) joue par `article_id` et non par URL : swipe une copie, la jumelle reste candidate.
- Les feedbacks sont par `article_id` aussi : liker une copie ne désactive pas l'autre, et un like sur la jumelle compte une deuxième fois les poids des keywords.
- L'enrichment tourne deux fois (deux LLM calls, deux extractions newspaper) pour un contenu identique — gaspillage direct de tokens.

**Hors scope.** Les titres identiques avec URLs différentes (rubriques hebdo "Politics", "Business", "Economic data…" du flux Economist) sont du faux-positif visuel : ce sont des articles distincts qui réutilisent un libellé. Pas de dédup heuristique par titre dans cette epic.

### Stories

- [x] **E15-S1** — `cron_fetch` skip d'une URL déjà ingérée pour ce user

---

#### [x] E15-S1 — `cron_fetch` skip d'une URL déjà ingérée pour ce user

**Contexte.** Aujourd'hui `_insert_articles` (`api/niouzou/crons/fetch.py:51`) déduplique uniquement sur `(source_id, miniflux_entry_id)`. Pour un même user, deux sources distinctes peuvent ingérer le même `url` parce qu'elles ont des `miniflux_entry_id` différents. On veut un *deuxième* niveau de dédup au point d'insertion : par `(sources.user_id, articles.url)`.

**Sémantique.**
- À l'insertion d'un batch fan-outé, pour chaque tuple `(source_id, url)` candidat : si une `articles` row existe déjà avec la même `url` ET appartenant à n'importe quelle `sources` row du même user, on **skip** l'insertion.
- Le premier flux qui a apporté l'article gagne ; les flux suivants ne créent rien. Pas de notion de "meilleure source" — c'est first-come-first-served, simple et déterministe.
- L'entrée Miniflux côté flux "perdant" est quand même marquée lue (E14-S1 s'en occupe au tick suivant — ou bien on l'ajoute au batch `handled_ids` ici, à confirmer dans le code, voir Acceptance).
- Aucune des copies skippées ne déclenche d'enrichment (par construction : pas d'`article` row → pas de pending → pas de cycle d'enrich).

**Acceptance.**
- Quand un `MinifluxEntry` matche une source dont le user a déjà un article avec la même URL via une autre source, aucune row n'est ajoutée et aucun appel d'enrichment n'est déclenché.
- Quand le même entry est matché par PLUSIEURS sources du même user dans le même batch (l'entry est récupéré une fois mais fan-outé), une seule row est insérée (la première du fan-out), les autres sont skippées.
- Quand deux users distincts ont chacun un source qui ingérerait la même URL : chacun a sa row (la dédup est *par user*, pas globale — sinon on casserait la sémantique multi-user actuelle où chaque user a son propre cycle d'impressions/feedback).
- L'entry Miniflux est marquée lue *même quand l'insertion est skippée* (sinon le pipeline rebascule dans le problème E14 : l'entry reviendrait à chaque tick).
- Log INFO : `cron_fetch: skipped N duplicate URL(s) already present for the user via another source`.

**Implémentation.**
- Avant l'INSERT, charger en une seule requête l'ensemble des `(sources.user_id, articles.url)` déjà présents pour les URLs du batch :
  ```sql
  SELECT s.user_id, a.url FROM articles a
  JOIN sources s ON s.id = a.source_id
  WHERE a.url = ANY(:urls_batch)
  ```
- Construire un set `existing: set[tuple[uuid.UUID, str]]`.
- Filtrer `values` : ne garder qu'une row si `(user_for_source[v.source_id], v.url) not in existing`. Au passage, tenir un *running set* sur les insertions de ce batch pour ne pas insérer deux copies issues du même batch (cas du fan-out d'un même entry sur deux sources du même user).
- L'`ON CONFLICT DO NOTHING` existant sur `(source_id, miniflux_entry_id)` reste — il garde sa raison d'être (retry safety).
- Les `MinifluxEntry.id` des "skippés" sont ajoutés à `handled_ids` (mark-as-read côté Miniflux) au même titre que les ingérées : du point de vue Miniflux, on a "traité" l'entry, on n'a juste pas créé d'`article` pour elle.

**Pas de migration**, pas de unique INDEX DB. Une vraie contrainte unique `(user_id, url)` nécessiterait de dénormaliser `user_id` dans `articles` (Postgres n'autorise pas de subquery dans une expression d'index unique). On reste sur la dédup applicative — `cron_fetch` étant single-replica, le risque de race est nul.

**Files.** `api/niouzou/crons/fetch.py`, `api/tests/test_cron_fetch.py`.

**Tests.**
- Pré-condition : un article (URL `U`) existe déjà via la source `S1` du user `A`. Un batch arrive avec un entry pointant sur `U` via la source `S2` du même user `A` → **0 nouvelle row**, l'entry est marqué lu côté Miniflux.
- Le même batch fan-outé sur `S1` + `S2` du user `A` (entry seul, deux sources du même user, aucune row préexistante) → **1 row insérée** (la première), entry marqué lu.
- Deux users distincts `A` et `B`, chacun a une source qui matche la même URL `U` → **2 rows** (une par user), l'entry est marqué lu une seule fois. La dédup ne se déclenche pas entre users.
- Régression : cas standard (entry unique, une seule source qui matche) → comportement identique à aujourd'hui.

---

### Notes E15

**Articles déjà en double en prod.** Cette story n'efface PAS les duplicates existants — elle empêche seulement les nouveaux. Les ~15 cartes en double dans le feed de Guillaume vont rester jusqu'à ce qu'elles sortent du fil naturellement (impressions au fur et à mesure des swipes) ou qu'on fasse un nettoyage explicite. À voir si on ouvre une story de cleanup séparée (script one-shot ou logique de read-time dedup dans `ranked_query`) — sujet pour une autre fois si l'utilisateur en ressent encore la gêne après E15-S1.

**Coût LLM évité.** Chaque doublon évité = un cycle d'enrichment évité (≈ 1 appel OpenRouter + 1 extraction newspaper). Sur Le Monde / Le Monde Sciences (~5–10 doublons par jour observés), c'est non négligeable sur la facture.

**Cohérence avec E14-S1.** Les deux fonctionnent ensemble : E14-S1 nettoie Miniflux des entries dont aucune source ne veut. E15-S1 dédup encore plus finement (deux sources la veulent mais on ne veut qu'une seule copie côté DB). Aucune interaction négative attendue.

---

## EPIC 16 — Smart Match : scoring sémantique par embeddings (juin 2026)

**Objectif** : ajouter un second moteur de scoring, **Smart Match**, basé sur des embeddings
sémantiques et un k-NN sur l'historique de feedback de l'utilisateur. Il coexiste avec le
moteur actuel (**Classic**, keywords + poids) derrière un toggle admin `scoring_mode`.
Classic reste le défaut et n'est PAS modifié.

> Dépend de EPIC 5 (enrichissement), EPIC 9 (feedback/poids), EPIC 10 (cron refresh, cold start).
> Remplace EPIC 12, abandonnée après audit (voir bannière E12).

**Problèmes résolus** (que E12 ne résolvait pas ou aggravait) :
- **P1 — fragmentation** : "IA" / "intelligence artificielle" / "LLM" sont quasi confondus dans
  l'espace d'embedding ; plus besoin de taxonomie ni de compaction pour accumuler du signal.
- **P2 — absence de sémantique** : deux articles sur le même sujet sans keyword commun
  partagent enfin du signal ; la polysémie ("transfert" rugby vs finance) est résolue par le contexte.
- **P3 — score figé à l'enrichissement** : en mode Smart Match les scores des articles récents
  sont **recalculés** chaque nuit — le feed profite enfin rétroactivement de l'apprentissage.

### Décisions de design

1. **Pas de profil utilisateur unique.** Un user aime le rugby ET l'informatique : la moyenne de
   ses embeddings serait un centroïde dans le vide sémantique entre les deux. Le scoring est
   *instance-based* (k-NN) : un article candidat n'est comparé qu'aux K feedbacks **les plus
   similaires** — un article rugby est jugé contre les likes rugby, jamais contre les likes Rust.
   Multi-modal par construction, zéro clustering, zéro hyperparamètre de "nombre de profils".
2. **Modèle d'embedding local** (sentence-transformers), pas OpenRouter : respecte la règle
   « le système doit marcher sans clé API ». Multilingue → résout FR/EN au passage.
   Modèle verrouillé (2026-06-10, après comparatif MTEB) : **`Qwen/Qwen3-Embedding-0.6B`** —
   top qualité multilingue de sa catégorie (MTEB ~64,3), Apache 2.0, 1024 dims (Matryoshka).
   ⚠️ Quasi irréversible : changer de modèle = re-backfill complet (vecteurs de modèles
   différents non comparables entre eux).
3. **pgvector, pas de vector DB dédiée.** Une extension Postgres, pas une 4ᵉ brique à self-hoster.
4. **`keyword_weights` continue de vivre dans les deux modes.** Le cron `refresh_weights` et le
   chemin feedback ne changent pas : l'écran Keywords reste alimenté, les overrides manuels
   restent des leviers (boost dans la formule Smart Match, cf. S5), et le retour au mode Classic
   est sans perte.
5. **Bascule de mode sans rescoring massif.** Les `article_relevance_scores` existants gardent
   leur valeur ; seuls les nouveaux scorings (enrichissement + rescoring nightly en mode smart)
   utilisent le moteur actif. La colonne `scorer` ('tfidf' | 'ai_keyword' | 'smart_match') trace la provenance.

### Formule Smart Match

Le signal par feedback réutilise la valeur E9-S1 : `value = (±1 reaction) + 0.5·saved + 0.5·read`.

```
liked(u)    = feedbacks de u avec value > 0 (embedding de l'article joint)
disliked(u) = feedbacks de u avec value < 0

S⁺ = Σ_{i ∈ topK(liked, sim)}    sim(a, eᵢ) · valueᵢ · decay(tᵢ)
S⁻ = Σ_{j ∈ topK(disliked, sim)} sim(a, eⱼ) · |valueⱼ| · decay(tⱼ)

raw   = S⁺ − λ·S⁻
score = sigmoid(β·raw + Σ_{kw pinnés ∩ keywords(a)} weight·salience)
```

- `sim` = similarité cosinus pgvector (`1 - (embedding <=> ...)`)
- `decay(t) = 0.5^(age_jours(t) / halflife)` — un like d'il y a 6 mois pèse moins qu'un like d'hier
- `raw = 0` (aucun feedback) → `score = 0.5` : même sémantique neutre que Classic, un nouveau user voit tout
- Défauts (clés `app_settings`) : `smart_topk = 5`, `smart_lambda = 0.8`, `smart_beta = 0.5`,
  `smart_decay_halflife_days = 90`, `smart_rescore_window_days = 14`
- `is_cold_start` en mode smart : TRUE ssi le user n'a aucun feedback avec `value > 0`

> Pas d'index ANN nécessaire : le k-NN se fait sur les articles *feedbackés du user* (quelques
> centaines de rows max), pas sur tout le corpus. `ORDER BY embedding <=> :a LIMIT K` sur cette
> jointure suffit largement. Un index HNSW est une optimisation future hors scope.

**Ordre de livraison** : S1 → S2 → S3 → S4 → S5. S6 est indépendante (livrable en parallèle).

### Stories

- [x] **E16-S1** — Infra : pgvector + colonne `articles.embedding`
- [x] **E16-S2** — Service d'embedding local + intégration `cron_enrich` + backfill
- [x] **E16-S3** — `SmartMatchScorer` (k-NN) + rescoring nightly
- [x] **E16-S4** — Toggle admin `scoring_mode` : Classic / Smart Match
- [x] **E16-S5** — Keywords pinnés comme boost + écran Keywords en mode smart
- [x] **E16-S6** — Canonicalisation organique du vocabulaire keywords — déjà couverte par E10-S2 (voir story)
- [x] **E16-S7** — Score breakdown en mode smart : voisins k-NN + pins au lieu des poids appris
- [x] **E16-S8** — Double score persistant : `keyword_score` ⊕ `smart_score` calculés ensemble (retrait TF-IDF)
- [x] **E16-S9** — `scoring_mode` = sélecteur du score actif (filtre seuil + tri) + rescore des deux + rename cron nocturne
- [x] **E16-S10** — PWA : affichage des deux scores côte à côte (chips keyword + smart)

---

#### [x] E16-S1 — Infra : pgvector + colonne `articles.embedding`

**Changements.**
- `docker-compose.yml` / `docker-compose.test.yml` : image `pgvector/pgvector:pg17` à la place
  de `postgres:17`. ⚠️ **Valider sur Colima d'abord** (`docker-compose pull` + démarrage) — le
  setup local a déjà produit des `exec format error` sur certaines images multi-arch
  (cf. CLAUDE.md). Si l'image pose problème, fallback : installer l'extension dans une image dérivée.
  ✅ Validé le 2026-06-10 : l'image pull et démarre sur Colima sans erreur.
- ⚠️ **Note migration de volume** (découvert à l'implémentation) : `docker-compose.yml` tournait
  en réalité sur `postgres:17-alpine` (musl). `pgvector/pgvector:pg17` est Debian/glibc — l'ordre
  de collation des index texte diffère. Sur un volume existant, exécuter une fois
  `REINDEX DATABASE niouzou;` (et `miniflux`) après le premier boot sur la nouvelle image
  (commentaire en place dans docker-compose.yml).
- Migration Alembic : `CREATE EXTENSION IF NOT EXISTS vector;` puis
  `ALTER TABLE articles ADD COLUMN embedding vector(1024);` (nullable — les articles non encore
  embeddés ont NULL).
- Modèle SQLAlchemy `Article` : colonne `embedding` (lib `pgvector` Python, type `Vector(1024)`).
- `docs/DATA_MODEL.md` mis à jour.

**Acceptance.**
- Migration passe sur DB vierge et DB peuplée ; rollback propre (drop column, l'extension reste).
- La stack `docker-compose` démarre sur Colima sans erreur.
- Les tests existants passent inchangés (la colonne est nullable, rien ne la lit encore).

---

#### [x] E16-S2 — Service d'embedding local + intégration `cron_enrich` + backfill

**Dépendance** : `sentence-transformers`, modèle **`Qwen/Qwen3-Embedding-0.6B`**
(1024 dims, ~600M params, ~1,2 Go disque ; RAM ~1,2 Go en fp16, ~2,4 Go en fp32 —
charger en fp16/bf16 par défaut, option ONNX int8 si le CPU cible rame). Ajouté dans
`api/pyproject.toml`. Choisi le 2026-06-10 après comparatif (vs gte-multilingual-base,
EmbeddingGemma, bge-m3, e5) : meilleure qualité multilingue de sa catégorie, licence
Apache 2.0 cohérente avec le projet, Matryoshka (troncature possible des dims sans recalcul).

**Nouveau composant** : `api/niouzou/services/embedding_service.py`
- Singleton de module, chargé **lazy** au premier appel (pas au boot de l'API : seuls le cron
  d'enrichissement et le backfill en ont besoin ; on évite ~1,2 Go de RAM résidente dans le
  process web).
- `embed(title: str, summary: str) -> list[float]` : embedde `title + " " + summary_executive`
  (ou `content[:1000]` en fallback). Normalisation L2 pour que `<=>` (cosinus) soit cohérent.
- **Pas d'instruction prompt** : Qwen3-Embedding est instruction-aware (préfixe côté "query"),
  mais notre usage est symétrique (article ↔ article) — tout est embeddé en mode document,
  sans instruction, uniformément. À figer dans le code avec un commentaire : mélanger des
  vecteurs avec/sans instruction casserait la comparabilité.

**Intégration `cron_enrich`** : après l'extraction de keywords, calculer et stocker l'embedding
dans la même transaction. **Toujours actif quel que soit le mode** (coût ~200-400 ms CPU/article,
négligeable au rythme du cron) : ainsi la bascule Classic → Smart Match est instantanée pour
les articles récents.

**Backfill** : commande CLI `python -m niouzou.tools.backfill_embeddings` — embedde par batch
de 50 tous les articles `embedding IS NULL`, ordonnés du plus récent au plus ancien,
interruptible/reprenable (idempotent par construction). Pas de bouton admin dans cette story.

**Tests** — ⚠️ le vrai modèle n'est JAMAIS chargé (cf. Notes E16) : tous les tests injectent
un faux encodeur (vecteurs synthétiques 1024d normés, déterministes).
- Article enrichi → `embedding` non NULL, dimension 1024, norme ≈ 1 (via le faux encodeur).
- Texte vide → pas d'exception, embedding du titre seul.
- Le loader n'est appelé qu'une fois par process (mock du loader, compteur d'appels).
- Backfill : 3 articles sans embedding → 3 embeddés ; relance → 0 travail.

**Acceptance.**
- `cron_enrich` embedde chaque nouvel article, quel que soit `scoring_mode`.
- L'API web ne charge jamais le modèle (vérifiable : import lazy non déclenché par le boot).
- Temps d'embedding < 1 s par article sur CPU.

---

#### [x] E16-S3 — `SmartMatchScorer` (k-NN) + rescoring nightly

**Nouveau composant** : `api/niouzou/scoring/smart_match.py`. Contrairement aux scorers
existants (purs, sans I/O), Smart Match a besoin de la DB (les voisins du user). Il ne rentre
donc PAS dans `BaseScorer` : c'est `ScoringService.score_article_for_user` qui branche selon
`scoring_mode` (lu via `settings_service`, une fois par run de cron).

```
async def smart_score(session, article_id, user_id) -> tuple[float, bool]:
    """Retourne (score, is_cold_start). Implémente la formule de l'epic en 2 requêtes :
    topK liked + topK disliked via ORDER BY embedding <=> :a LIMIT :k sur la jointure
    article_feedbacks × articles (embedding NOT NULL), puis calcul Python."""
```

- Article sans embedding (legacy non backfillé) → fallback transparent sur le scorer Classic
  actif (tfidf/ai_keyword), `scorer` stampé en conséquence. Aucun article ne reste sans score.
- `scorer = 'smart_match'` sur les rows scorées par ce chemin.
- Le boost keywords pinnés (S5) est intégré ici dès le départ (terme `Σ weight·salience` dans
  la sigmoïde) mais ne devient observable qu'avec S5 — pas de double implémentation.

**Rescoring nightly (le fix de P3)** : `cron_refresh_weights` gagne une étape, active uniquement
en mode smart : re-scorer `article_relevance_scores` des articles dont `created_at >` maintenant
− `smart_rescore_window_days` (la colonne s'appelle `created_at` = timestamp d'ingestion ;
`fetched_at` n'existe pas — corrigé à l'audit), pour tous les users concernés. Les rows plus anciennes restent
figées (elles sont déjà sorties du feed par la gravité). En mode Classic cette étape est un no-op.

**Tests** (embeddings de test = vecteurs synthétiques orthogonaux, pas le vrai modèle).
- User qui a liké 3 articles "rugby" (vecteurs proches) : article candidat proche → score > 0.5 ;
  article orthogonal ("bourse") → ≈ 0.5 (pas de pénalité : aucun voisin pertinent).
- **Multi-intérêts** : user avec deux clusters de likes (rugby, tech) orthogonaux → un candidat
  rugby ET un candidat tech scorent tous les deux > 0.5 ; un candidat à mi-chemin ne score pas
  mieux que les deux (pas d'effet centroïde).
- Dislikes proches du candidat → score < 0.5.
- Decay : un like vieux de 2×halflife pèse 4× moins qu'un like du jour.
- User sans feedback → score = 0.5, `is_cold_start = TRUE`.
- Article sans embedding → fallback Classic, `scorer != 'smart_match'`.
- Rescoring nightly : un score initial à 0.5 (user sans historique au moment de l'enrichissement)
  remonte après que le user a liké des articles similaires.

**Acceptance.**
- En mode smart, les nouveaux articles enrichis ont `scorer = 'smart_match'`.
- Le rescoring nightly ne touche que la fenêtre configurée et seulement en mode smart.
- Aucun changement de comportement quand `scoring_mode = 'classic'` (suite de tests existante intacte).

---

#### [x] E16-S4 — Toggle admin `scoring_mode` : Classic / Smart Match

**Setting** : clé `app_settings.scoring_mode`, valeurs `'classic'` (défaut) | `'smart'`.

**API admin** : exposée dans les settings existants (GET/PUT). Validation : `'smart'` refusé
avec 422 + message explicite si `sentence-transformers` n'est pas installé ou si l'extension
`vector` est absente de la DB.

**Admin UI** (écran Settings) : section "Scoring engine", deux choix radio :
- **Classic** — sous-titre « Keyword weights (current behavior) »
- **Smart Match** — sous-titre « Semantic similarity to your liked articles (beta) »

Sous le radio, une ligne d'état : `Embeddings: 1 240 / 1 312 articles (94 %)` — un simple
COUNT, pour que l'admin sache si un backfill (S2) vaut le coup avant de basculer. Pas de
bouton de backfill dans l'UI (CLI only, cf. S2).

**Sémantique de bascule** (documentée dans l'UI par une note) : le changement de mode affecte
les scorings *futurs* (enrichissement + rescoring nightly) ; les scores existants ne sont pas
recalculés à la bascule.

**Acceptance.**
- Défaut `'classic'` sur instance existante ET sur DB vierge (zéro changement de comportement au déploiement).
- La bascule ne déclenche aucun rescoring synchrone (réponse < 1 s).
- `npm run build` passe.

---

#### [x] E16-S5 — Keywords pinnés comme boost + écran Keywords en mode smart

**Contexte.** L'écran Keywords est un différenciateur produit : l'utilisateur voit et pilote ses
préférences. En mode smart, les poids *appris* ne pilotent plus le score (l'embedding s'en
charge), mais les poids *manuellement overridés* (`manually_overridden = true`) doivent rester
des leviers durs — c'est un contrat utilisateur.

**Changements.**
- Le terme `Σ_{kw pinnés ∩ keywords(article)} weight·salience` (déjà câblé en S3) est couvert
  par des tests dédiés : pin "rugby" à +5 → tout article portant le keyword "rugby" gagne le
  boost dans la sigmoïde, même si l'utilisateur n'a aucun like rugby.
- Écran Keywords en mode smart : bandeau informatif discret en haut de liste —
  « Smart Match actif : les poids appris sont indicatifs ; les poids épinglés 📌 restent appliqués au score. »
  Le mode courant est exposé via `GET /me` ou un endpoint settings public read-only (au choix de l'implémentation, documenter dans API_SPEC).
- Aucun changement aux interactions existantes (édition, pin, reset).

**Acceptance.**
- Pin positif/négatif observable sur le score d'un article test en mode smart.
- En mode classic, l'écran Keywords est strictement inchangé (pas de bandeau).

---

#### [x] E16-S6 — Canonicalisation organique du vocabulaire keywords (les deux modes)

> ✅ **Constat d'audit (2026-06-10) : déjà couverte par E10-S2.** Le « vocab nudge » existant
> fait exactement ce que demande cette story, en mieux ciblé : `cron_enrich._load_top_keywords`
> injecte les 200 termes les plus fréquents (un `GROUP BY count(*)` par run de cron, pas par
> article) dans le prompt du **call combiné d'enrichissement** — c'est lui qui extrait les
> keywords depuis E13, pas `scoring.ai_keywords` que cette story visait — avec la consigne
> `Existing vocabulary (reuse when applicable): …` et un cap en caractères pour ne jamais
> écraser l'article (régression corrigée en E10-S2). Pas de filtrage côté Python : le
> vocabulaire converge sans être contraint, exactement la sémantique voulue ici. Les tests
> demandés existent : `test_generate_enrichment_injects_vocab` (les termes apparaissent dans
> le prompt) ; le cas « instance vide » est le défaut de tous les tests `EnrichmentService`
> (vocab vide → pas de ligne vocabulaire, pas d'erreur) et est exercé sur le chemin cron par
> `test_run_closes_openrouter_client` (`_load_top_keywords` → `[]`). Aucun code ajouté pour S6.

**Contexte.** Seule survivante d'E12 : réduire la fragmentation des keywords ("IA" vs
"intelligence artificielle") SANS taxonomie hardcodée. Utile dans les deux modes (en classic
pour les poids, en smart pour la lisibilité de l'écran Keywords et la précision des pins).

**Changement** (`enrichment_service` / prompt `scoring.ai_keywords` en DB) :
- Injecter dans le system prompt les ~100 termes les plus fréquents de l'instance
  (`SELECT term FROM article_keywords GROUP BY term ORDER BY count(*) DESC LIMIT 100`,
  calculé une fois par run de cron, pas par article).
- Consigne ajoutée : *« Quand un concept de l'article correspond à un terme de cette liste,
  réutilise exactement ce terme plutôt qu'une variante. Les concepts absents de la liste
  restent libres. »*
- Pas de filtrage côté Python : le vocabulaire reste ouvert, il *converge* au lieu d'être contraint.
- Le fallback TF-IDF est inchangé (il n'a pas de problème de variantes — il recopie le texte).
- La compaction E10-S3 reste le filet de sécurité pour l'existant.

**Tests.**
- Le prompt envoyé contient les termes les plus fréquents (mock OpenRouter, assertion sur le system).
- Instance vide (0 keywords) → prompt sans section vocabulaire, pas d'erreur.

**Acceptance.**
- Sur un corpus de test où "intelligence-artificielle" domine, un nouvel article IA réutilise le
  terme canonique (vérifiable en mock en faisant retourner la variante par le LLM : le terme
  reste accepté — la convergence est *incitative*, pas un filtre).

---

#### [x] E16-S7 — Score breakdown en mode smart : voisins k-NN + pins au lieu des poids appris

**Contexte.** Le popup "Score breakdown" (E10-S2 : `GET /articles/{id}/score-debug` +
`ScoreDebugSheet.tsx`) explique un score classic par la liste des keywords de l'article et les
poids appris du user. Sur un article scoré `smart_match`, cette vue devient trompeuse : le label
scorer tombe sur `'—'` (mapping inconnu) et les poids affichés laissent croire qu'ils ont produit
le score, alors qu'en smart seuls les pins y contribuent — le score vient des k plus proches
voisins likés/dislikés. Trou de spec identifié après livraison S1-S6.

**Changements.**
- **API** — `GET /articles/{id}/score-debug` : quand la row `article_relevance_scores` du user
  porte `scorer = 'smart_match'`, le payload gagne trois champs (absents/null sinon — payload
  classic strictement inchangé) :
  - `liked_neighbors` / `disliked_neighbors` : les top-K feedbacks les plus similaires par
    polarité — `{title, similarity, value, age_days, contribution}` avec
    `contribution = similarity × |value| × decay(age_days)` ;
  - `pins` : le détail du boost pins — `{term, weight, salience, contribution}` avec
    `contribution = weight × salience` (uniquement les `manually_overridden` ∩ keywords de l'article).
- Réutiliser les requêtes existantes de `scoring/smart_match.py` (top-K + pins), étendues pour
  remonter le titre du voisin — pas de double implémentation de la formule. Les paramètres
  (`smart_topk`, halflife…) sont lus des settings effectifs au moment de l'appel.
- ⚠️ **Sémantique assumée** : les voisins sont recalculés à l'ouverture du popup, pas stockés —
  ils peuvent différer marginalement de ceux qui ont produit le score persisté (nouveaux
  feedbacks depuis). Le rescoring nightly garde l'écart faible ; acceptable pour une vue debug.
- **PWA** (`ScoreDebugSheet.tsx`) : mapping label `smart_match` → « Smart Match ». Quand le
  scorer est `smart_match` : sections « Closest to your likes » / « Closest to your dislikes »
  (titre tronqué + sim + contribution signée), section « Pinned keywords » si non vide, et note
  « Learned weights are indicative in Smart Match — they don't affect this score. » à la place
  de la liste keywords/poids. En classic : rendu strictement inchangé.
- `docs/API_SPEC.md` mis à jour.

**Tests** (vecteurs synthétiques, pattern test_smart_match).
- Article smart avec 2 likes proches + 1 dislike proche → payload : voisins dans la bonne
  polarité, `similarity` ≈ attendue, `contribution` décroissante avec l'âge, pins listés avec
  `weight × salience`.
- Article classic (`scorer = 'tfidf'`) → payload identique à avant S7 (champs smart absents).
- Article `smart_match` dont l'embedding a disparu (cas dégénéré) → champs smart vides, pas d'erreur.

**Acceptance.**
- En classic, payload et rendu pixel-identiques à avant.
- Sur un article smart : label « Smart Match », voisins par polarité, pins visibles, aucun
  poids appris affiché comme contributif.
- `npm run build` passe.

---

#### [x] E16-S8 — Double score persistant : `keyword_score` ⊕ `smart_score` calculés ensemble (retrait TF-IDF)

> ✅ **Livrée (2026-06-11).** Migration `d8e2f5a91c47` (backfill par provenance `scorer`,
> validée upgrade + downgrade sur la DB de test). `enrichment_method` devient `'ai'` | NULL
> (plus de `'tfidf'` sur les nouvelles rows ; les stats E7-S15 gardent les rows legacy).

**Contexte.** Nouvelle vision (remplace l'approche « un seul score, sélectionné par le mode » de
S3) : les **deux méthodes de scoring coexistent en permanence** sur chaque article, calculées
ensemble à l'enrichissement, pour pouvoir les **comparer en continu**. `scoring_mode` ne décide
plus *lequel* est calculé (les deux le sont toujours) — il ne fait que choisir lequel pilote les
filtres feed/explore (→ S9). Effet de bord bienvenu : le flip de mode devient instantané (les deux
colonnes sont toujours présentes, plus aucun rescore requis au changement de mode).

Cette story absorbe l'ancien fix de séquencement (embedding avant scoring) : puisqu'on score les
deux dans la foulée, l'embedding est calculé avant.

**Retrait TF-IDF (décision actée).** Le fallback TF-IDF est **supprimé du chemin d'enrichissement**.
L'extraction de keywords devient **LLM-only** ; si OpenRouter/LLM est indisponible → pas de keywords
→ `keyword_score = NULL` → l'article se comporte côté keyword comme pour un nouveau user (badge
« – »). L'embedding étant **local**, `smart_score` reste calculé sans IA. Conséquence assumée :
sans IA, le mode smart reste 100 % fonctionnel, mais les features keyword (score keyword, **pins**,
écran Keywords, badges) deviennent AI-only. ⚠️ Mettre à jour l'invariant `CLAUDE.md` (« AI optional
— must work fully without it ») et la note « Coût » d'E16 : « marche sans IA » se restreint au
pathway smart.

**Modèle de données — `article_relevance_scores`.** PK inchangée `(article_id, user_id)`.
- **Ajout** :
  - `keyword_score` Float **NULL** — score keyword (AI-keywords × poids user) ; `NULL` quand
    l'article n'a aucun keyword (LLM indispo à l'enrichissement).
  - `keyword_cold_start` Bool NOT NULL default false — aucun keyword de l'article dans le vocab du
    user (sémantique de l'actuel `is_cold_start`).
  - `smart_score` Float **NULL** — score k-NN ; `NULL` quand l'article n'a pas d'embedding.
  - `smart_cold_start` Bool NOT NULL default false — le user n'a aucun feedback positif (définition
    cold du mode smart, cf. S3).
  - CheckConstraint `[0,1]` sur chaque score quand non-NULL.
- **Suppression** : `relevance_score`, `scorer`, `is_cold_start`. La colonne `scorer` devient
  redondante (TF-IDF retiré → keyword = toujours `ai_keyword`, smart = toujours `smart_match` ;
  l'identité de la colonne *est* la méthode). `articles.enrichment_model` (quel LLM) reste.
- **Migration Alembic** : ajouter les 4 colonnes ; backfill depuis l'existant
  (`scorer = 'smart_match'` → `smart_score := relevance_score`, `smart_cold_start := is_cold_start` ;
  sinon → `keyword_score := relevance_score`, `keyword_cold_start := is_cold_start`) ; la méthode
  non encore calculée reste `NULL` (badge « – ») jusqu'au prochain passage nocturne (S9) — acceptable
  sur un parc self-host ; puis `DROP` des 3 anciennes colonnes.

**Scoring — `ScoringService`.**
- `score_article_for_user` calcule et upsert **les deux** scores dans l'unique row, **indépendamment
  de `scoring_mode`** :
  - `keyword_score` via le pipeline keyword **si** l'article a des keywords (le LLM en a produit),
    sinon `NULL` ;
  - `smart_score` via `smart_score()` **si** l'article a un embedding, sinon `NULL` ;
  - + les deux flags cold.
- Suppression du branchement « smart sinon fallback Classic » et de **tout** le chemin TF-IDF dans
  l'enrichissement (`tfidf_scoring`, `TFIDFScorer`, double `ScoringService`) — seul `AIKeywordScorer`
  subsiste pour l'extraction. La classe `TFIDFScorer` peut rester pour les tests unitaires du
  pipeline mais n'est plus jamais branchée par `cron_enrich`.
- **`crons/enrich.py::enrich_article`** — nouvel ordre : extraction → enrichissement LLM
  (résumé + keywords) → store keywords (si présents) → **embedding** (`await session.flush()` pour
  que le `SELECT Article.embedding` du smart voie le vecteur frais dans la même transaction) →
  **scoring des deux** → transition `enriched`. Mettre à jour le docstring d'en-tête (liste des
  étapes) et retirer la mention du fallback TF-IDF.
- Échec LLM sur un article → pas de keywords stockés, `keyword_score = NULL`, mais embedding (local)
  calculé → `smart_score` présent. L'article est quand même `enriched` et surface.

**Pins inchangés** : `pinned_breakdown` joint toujours `article_keywords` ↔ `keyword_weights`
épinglés ; sans keywords (LLM down) le boost est simplement vide.

**Tests** (pattern `test_enrich` + faux encodeur `fake_embeddings`, jamais le vrai modèle).
- LLM on + embedder on → `keyword_score` ET `smart_score` non-NULL après enrichissement (quel que
  soit `scoring_mode`).
- LLM off (aucun keyword) → `keyword_score = NULL`, `smart_score` non-NULL.
- embedder `None` → `smart_score = NULL`, `keyword_score` non-NULL.
- Les deux off → les deux `NULL`, article quand même `enriched` (badge « – »/« – »).
- Aucun chemin n'atteint `TFIDFScorer` depuis `cron_enrich` (le double `ScoringService` a disparu).
- Migration : une row legacy `scorer='smart_match'` → `smart_score` rempli, `keyword_score` NULL ;
  une row `scorer='ai_keyword'` → l'inverse.

**Acceptance.**
- Tout article fraîchement enrichi a **les deux** colonnes peuplées quand LLM + embeddings sont dispo,
  indépendamment de `scoring_mode`.
- Plus aucune trace de TF-IDF dans le chemin d'enrichissement.
- LLM down → `keyword_score = NULL`, `smart_score` présent ; l'article surface quand même.

**Docs à mettre à jour.**
- `DATA_MODEL.md` — table `article_relevance_scores` : nouvelles colonnes (`keyword_score`,
  `keyword_cold_start`, `smart_score`, `smart_cold_start`), suppression de `relevance_score`/`scorer`/
  `is_cold_start`, contraintes ; mettre à jour la définition de `article.relevance_score` et le glossaire.
- `ARCHITECTURE.md` — décrire le double scoring à l'enrichissement, le retrait TF-IDF, le nouvel ordre
  des étapes `enrich_article` ; clarifier que « marche sans IA » = pathway smart uniquement.
- `CONVENTIONS.md` — la règle « `ScoringPipeline` seul point d'entrée des scorers classic » et le rôle
  de `ScoringService.score_article_for_user` (calcule désormais les deux scores).
- `CLAUDE.md` — invariant « AI optional » restreint au mode smart ; tableau « Scoring » (plus de
  TF-IDF fallback) ; concept `relevance_score` → deux scores.

---

#### [x] E16-S9 — `scoring_mode` = sélecteur du score actif (filtre + tri) + rescore des deux + rename cron nocturne

> ✅ **Livrée (2026-06-11).** Valeurs de `scoring_mode` renommées `'keyword'` | `'smart'`
> (whitelist de la story) ; `'classic'` reste accepté comme alias legacy, normalisé en
> `'keyword'` à la lecture, et la migration réécrit la row `app_settings` existante.
> Env var : `CRON_NIGHTLY_REFRESH_HOUR`, avec fallback de lecture sur l'ancienne
> `CRON_REFRESH_WEIGHTS_HOUR` (transition Railway sans coupure).

**Contexte.** Avec les deux scores persistés (S8), `scoring_mode` cesse de gater le calcul et devient
le **sélecteur du score actif** pour le feed/explore. Le score actif pilote **à la fois** le filtre
de seuil **et** le tri par gravité (décision : les deux, pour rester cohérent — on filtre et on
classe avec le même score). Comme les deux colonnes sont toujours présentes, **changer de mode est
instantané** : aucun rescore ni migration.

**Changements — ranking (`services/ranked_query.py`).**
- La colonne de score active + le flag cold actif sont choisis selon `scoring_mode` (lu une fois par
  requête depuis les settings effectifs ; whitelist `{keyword, smart}` → nom de colonne bindé sans
  risque d'injection).
- `FEED_RANK` : `(CASE WHEN <active_cold> OR <active_score> IS NULL THEN 0.5 ELSE <active_score> END)`
  — un score actif `NULL` (méthode indispo pour cette row) est traité **comme cold** : baseline 0.5,
  l'article surface au lieu d'être caché.
- Filtre de seuil : `(<active_score> >= :threshold OR <active_cold> = TRUE OR <active_score> IS NULL)`.
- Projection `RANKED_COLUMNS` / `FeedArticle` : renvoyer **les deux** scores + les deux flags cold
  (et l'indication de la méthode active), pour l'affichage S10. `schemas/feed.py` + types PWA mis à
  jour. (`scorer` retiré du payload.)

**Changements — rescore nocturne + rename.**
- Le rescore ne dépend plus du mode (les deux scores sont toujours vivants) : il **rafraîchit les
  deux** colonnes pour les articles de la fenêtre `smart_rescore_window_days`. Sans ça, `keyword_score`
  figé à l'enrichissement divergerait des poids recalculés chaque nuit → comparaison faussée.
  `rescore_recent_smart` → `rescore_recent` (retire le gate `if mode != 'smart': return 0`).
- **Rename du cron (demande explicite)** — nom polyvalent pour les deux modes :
  `crons/refresh_weights.py` → `crons/nightly_refresh.py` ; logger `cron_refresh_weights` →
  `cron_nightly_refresh` ; job worker `_refresh_weights_job` → `_nightly_refresh_job` ; setting
  `cron_refresh_weights_hour` → `cron_nightly_refresh_hour`. Le job fait toujours : recompute des
  poids keyword (`recompute_all`) + demote des cold flags + `rescore_recent`. ⚠️ Note déploiement :
  renommer aussi la variable d'env sur Railway (`CRON_NIGHTLY_REFRESH_HOUR`) — lire l'ancienne en
  fallback le temps d'une transition, ou couper net et mettre à jour la config.
- `demote_cold_flags` opère désormais sur `keyword_cold_start` (le cold smart est feedback-based,
  géré par `rescore_recent`).

**Tests.**
- `scoring_mode = 'keyword'` → feed filtré/trié sur `keyword_score` ; `'smart'` → sur `smart_score`.
- Flip de mode → l'ordre du feed change **sans** rescore ni écriture DB.
- Score actif `NULL` → article traité comme cold (surface, bypass seuil, baseline 0.5).
- `rescore_recent` rafraîchit **les deux** colonnes dans la fenêtre, quel que soit le mode.
- API : `/feed` et `/explore/new` renvoient `keyword_score`, `smart_score` + flags pour chaque row.

**Acceptance.**
- Changer `scoring_mode` dans l'admin change instantanément le classement feed/explore, sans
  migration ni rescore.
- L'API renvoie les deux scores pour chaque article.
- Le cron nocturne renommé tourne pour les deux modes et rafraîchit les deux scores.

**Docs à mettre à jour.**
- `API_SPEC.md` — payloads `/feed` et `/explore/new` : champs `keyword_score`, `smart_score`, flags
  cold, `active_method` (retrait `scorer`) ; sémantique de `scoring_mode` (sélecteur, plus gate).
- `ARCHITECTURE.md` — `scoring_mode` comme sélecteur du score actif (filtre + tri), flip instantané ;
  rename du cron nocturne et de l'env var ; liste des variables d'environnement (`SCORING_MODE`,
  `CRON_NIGHTLY_REFRESH_HOUR`, anciennes retirées).
- `CONVENTIONS.md` — renommage `crons/refresh_weights.py` → `crons/nightly_refresh.py` si un cron y
  est listé.
- `CLAUDE.md` — section « Repo structure » (`crons/`) + « Environment variables » (rename).

---

#### [x] E16-S10 — PWA : affichage des deux scores côte à côte (chips keyword + smart)

**Contexte.** Surfacer les deux méthodes pour comparaison directe. Choix retenu : **deux chips côte
à côte** sur la carte (et la vue détail), plutôt qu'une seule chip + breakdown.

**Changements (`ScoreBadge.tsx`, `ArticleCard`, `ScoreDebugSheet.tsx`).**
- En haut à droite de l'article : **deux chips** — keyword (icône `Hash` #) et smart (icône `Radar`),
  chacune affichant son `%` ou « – » (score `NULL` ou cold). La chip **active** (selon `scoring_mode`,
  donné par l'API) est mise en avant (fond accent plein) ; l'autre est atténuée (outline/muted). Plus
  d'icône `Sparkles` (TF-IDF/AI distinction supprimée : keyword = toujours AI).
- « – » unifié = score actif de cette méthode absent (`NULL`) **ou** cold-start de cette méthode.
- Le popup « Score breakdown » affiche **toujours les deux sections** quelle que soit la méthode
  active : section keyword (liste keywords + poids, cf. rendu classic existant) **et** section smart
  (voisins likés/dislikés + pins, cf. S7), chacune avec son `%`. Le payload `score-debug` renvoie les
  deux jeux de données (réutilise S7 pour le smart ; garde la liste keywords/poids pour le keyword).
- Types PWA (`types/api.ts`) : `FeedArticle` / `ArticleDetail` gagnent `keyword_score`,
  `keyword_cold_start`, `smart_score`, `smart_cold_start`, `active_method` ; `scorer` retiré.

**Tests / acceptance.**
- Une carte montre les deux chips ; l'active est visuellement distincte ; « – » quand une méthode est
  NULL/cold.
- Le breakdown montre les deux méthodes simultanément.
- `npm run build` passe ; `BlobBackground` toujours présent ; styles issus de `DESIGN_SYSTEM.md`.

**Docs à mettre à jour.**
- `DESIGN_SYSTEM.md` — documenter les deux chips de score (keyword/smart), états actif/atténué et « – ».
- `API_SPEC.md` — payload `score-debug` renvoyant les deux sections (keyword + smart) simultanément.

---

### Notes E16

**RAM.** Le modèle (~1,2 Go chargé en fp16) tourne dans le process cron, en lazy — le process
web ne le charge jamais. La cible de déploiement est Railway, où la marge RAM est confortable.
En dev local (Colima 2 GiB), augmenter la VM si on veut faire tourner l'enrichissement complet
(`colima start --memory 4`) ; les tests, eux, ne chargent JAMAIS le modèle (cf. règle ci-dessous).
Documenter ~1,5 Go de RAM additionnelle recommandée dans le README self-host.

**Règle de test absolue : le modèle d'embedding est une boîte noire, toujours mocké.**
Aucun test, à aucun niveau (unit, intégration, CI), ne télécharge ni ne charge
`Qwen3-Embedding-0.6B`. `embedding_service` expose un point d'injection (même pattern que
`OpenRouterClient` dans les scorers) ; les tests injectent un faux encodeur retournant des
vecteurs synthétiques déterministes (1024 dims, normés). Vérifier la qualité réelle du modèle
n'est pas le travail de la suite de tests.

**Un seul vecteur par article — pas de chunking (délibéré).** On embedde `title + summary_executive`
(~100-200 mots), pas le contenu intégral : le résumé condense déjà le sujet, et un article de
presse est essentiellement mono-sujet. Le chunking (N vecteurs/article + agrégation max-sim)
se justifie pour du retrieval fin sur documents longs, pas ici — il multiplierait stockage et
complexité du k-NN pour un gain marginal. La multi-modalité qui compte est au niveau du *user*
(plusieurs centres d'intérêt), et elle est traitée par le k-NN top-K, pas par le découpage des
articles. Si un besoin passage-level émerge un jour (très longs formats), ce sera une epic dédiée.

**Coût.** Zéro coût API : l'embedding est local. À l'inverse, en mode smart on POURRAIT
économiser l'appel LLM d'extraction de keywords — on ne le fait PAS : les keywords restent
nécessaires (écran Keywords, pins, badges, retour lossless au mode classic).

**Pourquoi pas de `kind`/badges (E12-S1/S4) ?** Sans taxonomie ni NER, tous les keywords ont la
même provenance (extraction LLM ou TF-IDF, déjà tracée par `article_relevance_scores.scorer`).
La colonne `kind` n'aurait plus rien à distinguer.

**Évolutions futures hors scope** : index HNSW si le corpus dépasse ~100k articles ; centroïdes
multi-clusters (HDBSCAN, similarité max) si le k-NN devient coûteux ; "similar articles" dans
l'UI détail article (gratuit avec pgvector, une story d'une autre epic).

---

## EPIC 17 — Follow-ups (juin 2026)

**Objectif** : lot de retours d'usage post-déploiement Railway — lisibilité du suivi de coût,
navigation au retour d'un article, recherche textuelle dans Explore, réduction de la conso
serveur, et remise à zéro du moteur de reco.

> Chaque story porte une **décision ouverte** à trancher avec le mainteneur avant dev (cf.
> "Questions ouvertes"). Statut initial : ⛔ en attente d'arbitrage, sauf indication.

### Stories

- [x] **E17-S1** — Suivi de coût OpenRouter : afficher des centimes (+ vérifier la capture en prod)
- [x] **E17-S2** — Retour d'un article ouvert : rester sur l'article, ne pas avancer le feed
- [x] **E17-S3** — Recherche textuelle dans la vue Explore
- [x] **E17-S4** — Réduire la conso serveur Railway (décharge modèle entre runs + intervalle 15→30)
- [x] **E17-S5** — Reset de l'historique de feedback (moteur de reco vierge)
- [x] **E17-S6** — Retours round 2 : coût replié dans « Pipeline · Last », recherche (filtres masqués dès la frappe + reset au navigate sauf retour article), compteurs d'articles par source

---

#### [x] E17-S1 — Suivi de coût OpenRouter : afficher des centimes

**Problème adressé** :

Le System panel affiche `1h · $0   6h · $0   24h · $0`. `Profile.tsx:formatCost` rend `$0`
dès que la valeur vaut exactement 0, et 4 décimales sinon. Voir partout `$0` (et non `$0.0000`)
signifie que les fenêtres remontent **exactement 0** → soit le coût réel est nul, soit la
capture est cassée en prod (le lookup best-effort `/generation` de `OpenRouterClient._record_usage`
échoue systématiquement sur Railway → `cost_usd = 0` pour chaque ligne). Reformater en centimes
ne corrige pas ce second cas.

**Approche proposée** :

1. **Diagnostic d'abord** : interroger `llm_usage_log` en prod (`sum(cost_usd)`, `max(cost_usd)`,
   nb de lignes récentes). Si tout est à 0 alors qu'il y a eu de l'enrichissement → la capture
   est le vrai bug (corriger le lookup `/generation`, ou récupérer `usage.cost` autrement).
2. **Affichage** : exprimer en centimes (`¢`/centimes €) avec assez de décimales pour rendre
   visibles les montants sub-cent d'un run typique, au lieu de retomber sur `$0`.

**Questions ouvertes** : la valeur prod est-elle réellement 0 (→ bug de capture prioritaire) ou
juste mal formatée ? Unité voulue : centimes de dollar (`¢`) ou centimes d'euro ?

**Acceptance** : le panel rend un montant lisible en centimes ; si la capture était cassée, les
nouveaux runs loguent un `cost_usd` non nul. Docs touchées : `docs/API_SPEC.md` si le format de
`/stats.llm_cost` change.

---

#### [x] E17-S2 — Retour d'un article ouvert : rester sur l'article

**Problème adressé** :

Depuis Explore (Lus/Nouveaux) ou Saved, ouvrir un article fait `navigate('/?start=id')` → le
Feed se positionne sur l'article (E9-S3). En revenant (retour navigateur / edge-swipe, ou retour
au PWA après ouverture du lien externe via `window.open`), le feed n'est plus sur l'article
ouvert : le `visibilitychange` de `Feed.tsx:119-138` relance `refresh()` après un délai, ce qui
recharge le deck depuis le haut → effet "next". L'attendu : revenir **sur l'article**.

**Approche proposée** (à confirmer selon le scénario retenu) :

- Si scénario = retour au PWA après `window.open` du lien externe : ne pas déclencher le refetch
  de visibilité quand l'absence vient d'une ouverture d'article (flag/timestamp posé à
  l'ouverture), ou restaurer la position (scroll vers l'article actif) après refetch.
- Si scénario = back navigation Explore→Feed : préserver/rétablir l'article courant (mémoriser
  l'id actif, re-pivoter dessus au retour). Cohérent avec le pattern sessionStorage déjà utilisé
  pour Explore (cf. note edge-swipe = full reload, pas popstate SPA).

**Décision actée** : couvrir **les deux** chemins. (a) Retour au PWA après ouverture du lien
externe : ne pas relancer le refetch de visibilité lorsque l'absence vient d'une ouverture
d'article. (b) Back Explore→Feed : préserver/rétablir l'article courant pour ne pas afficher le
suivant.

**Acceptance** : après ouverture d'un article puis retour, l'utilisateur retrouve ce même
article (pas l'article suivant ni le haut du feed).

---

#### [x] E17-S3 — Recherche textuelle dans Explore

**Problème adressé** :

Aucun moyen de retrouver un article par mot-clé : Explore n'offre que les tabs Lus/Nouveaux +
filtres score/source. Besoin d'une recherche plein texte sur l'ensemble des articles.

**Approche proposée** :

- Backend : nouvel endpoint (ou query param `q=`) de recherche sur `articles`, scoping aux
  articles visibles de l'utilisateur. Champs candidats : `title`, `summary_executive`,
  `content`. Implémentation : `ILIKE` simple d'abord, ou full-text Postgres (`tsvector` +
  `websearch_to_tsquery`) si on veut du ranking/stemming. Réutiliser la pagination cursor
  d'Explore.
- Frontend : champ de recherche dans le header Explore ; débounce ; réutilise `ArticleListRow`.
  Interaction avec les tabs/filtres à définir.

**Décision actée** : recherche serveur **`ILIKE` simple** sur `title` + `summary_executive`,
sur **tous les articles de l'utilisateur** (Lus + Nouveaux confondus). Pas de full-text/tsvector
pour cette story. Champ de recherche dans le header Explore (débounce), réutilise `ArticleListRow`
et la pagination cursor.

**Acceptance** : taper une requête dans Explore filtre la liste sur les articles correspondants ;
résultats paginés ; doc `docs/API_SPEC.md` mise à jour.

---

#### [x] E17-S4 — Réduire la conso serveur Railway

**Problème adressé** :

Coût/conso Railway jugés trop élevés. Deux pistes évoquées : passer en "serverless", et/ou
réduire la fréquence des fetchs.

**Nature** : **analyse + décision avant tout code.** "Serverless" n'est pas trivial sur cette
stack — l'API FastAPI peut tolérer le scale-to-zero, mais le `refresh-worker` (cron fetch/enrich
+ modèle d'embedding ~1,2 Go chargé en lazy) est un process long/stateful mal adapté au
serverless ; Miniflux et Postgres sont des services persistants. La piste la plus rentable et
sûre à court terme est probablement **espacer les crons** (intervalle fetch/enrich) et **ajuster
les ressources/replicas**, pas une réécriture serverless.

**Approche proposée** : produire d'abord un constat (où part la conso : web idle vs worker vs
DB ; relire `railway status` + métriques + intervalles cron actuels), puis livrer le(s) quick
win(s) validés (ex. augmenter l'intervalle entre fetchs via les env `CRON_*`).

**Décision actée** : **analyse + quick wins low-risk uniquement** (pas de scale-to-zero, pas de
migration serverless pour l'instant). Livrable : note d'analyse de la conso (web/worker/DB +
intervalles cron actuels) puis ajustement des intervalles de cron fetch/enrich via env `CRON_*`
si la fraîcheur le permet.

**Analyse (juin 2026)** :

État Railway : 5 services Online — `api`, `pwa`, `miniflux`, `refresh-worker`, `Postgres`
(volume 0,4/4,9 Go). Le poste de conso dominant est le **`refresh-worker`** : il exécute le cycle
fetch + enrich (extraction contenu + appel LLM d'enrichissement + calcul d'embedding local
Qwen3-0.6B) **toutes les 15 min** (`CRON_FETCH_INTERVAL=15`), soit ~96 runs/jour. Le modèle
d'embedding (~1,2 Go) reste chargé en RAM dans le process worker entre les runs (lazy, chargé une
fois) ; le CPU n'est sollicité qu'au moment des runs. Threads déjà plafonnés
(`EMBEDDING_NUM_THREADS=3`, `OMP_NUM_THREADS=3`, cf. note "Railway worker threading"). L'`api` et
le `pwa` sont peu coûteux (web idle). Le refresh nocturne (`CRON_REFRESH_WEIGHTS_HOUR=3`) est
ponctuel.

**Quick win recommandé** : porter `CRON_FETCH_INTERVAL` de **15 → 30 min** (voire 60) sur le
service `refresh-worker`. Effet : ~2× (resp. 4×) moins de runs d'enrichissement/embedding → la
principale source de CPU baisse d'autant. Coût : fraîcheur du feed un peu moins immédiate
(articles visibles avec ~15-45 min de retard supplémentaire au pire). Aucun changement de code —
juste une variable d'env. **À appliquer après validation du mainteneur** (impacte la fraîcheur,
config production) : `railway variables --service refresh-worker --set CRON_FETCH_INTERVAL=30`.

**Serverless Railway — investigué, écarté pour ce worker** : le vrai poste de conso est le
**modèle d'embedding (~1,2 Go) résident en RAM 24/7**. L'**App Sleeping** Railway ne convient pas :
d'après la doc, un service s'endort après 10 min **sans trafic sortant** (le pool Postgres ouvert
le maintient éveillé) et se **réveille sur requête entrante** — or le planning du worker est
*interne* (APScheduler), donc s'il s'endormait, rien ne le relancerait sur le créneau →
l'enrichissement s'arrêterait. Le primitif correct serait **Railway Cron Jobs** (run-to-completion,
vrai scale-to-zero) mais il impose une re-archi lourde (entrypoint one-shot, **verrou advisory
Postgres** pour remplacer le lock in-process partagé avec `POST /admin/refresh`, modèle embarqué
dans l'image pour éviter un re-téléchargement de 1,2 Go par run, cold-start par run) → reporté en
epic dédiée si besoin.

**Solution retenue (réalisée)** : **décharger le modèle entre les runs** + **espacer l'intervalle**.
- `embedding_service.unload_embedding_model()` libère le modèle (`gc.collect()`) après chaque cycle ;
  no-op pour les encodeurs injectés (tests). Appelé dans le `finally` de `_guarded_run`
  (`refresh_worker`), exécuté en thread. Rechargement lazy au run suivant (petit cold-start contre
  RAM idle quasi nulle). Archi inchangée : verrou + bouton admin préservés.
- `CRON_FETCH_INTERVAL` porté de 15 → **30 min** sur `refresh-worker` (appliqué en prod).

**Acceptance** : note d'analyse livrée ; RAM idle du worker libérée entre les runs (modèle déchargé) ;
intervalle de fetch espacé en prod. ✅

---

#### [x] E17-S5 — Reset de l'historique de feedback (moteur de reco vierge)

**Problème adressé** :

Pouvoir repartir d'un moteur de reco vierge : effacer l'historique des likes/dislikes/etc. pour
ré-entraîner les préférences de zéro.

**Approche proposée** :

- Service (jamais dans le router) qui purge, pour l'utilisateur courant, les données de
  préférence apprises. À cadrer précisément (cf. questions) : événements de `feedback`,
  `keyword_weight`, et éventuellement les scores persistés / `seen` impressions.
- Endpoint dédié (POST, idempotent) + bouton dans Profile avec **confirmation** (action
  destructive, irréversible).

**Décision actée** : purge **feedback + `keyword_weight`** pour l'utilisateur courant → reco
vraiment vierge immédiatement. Le statut "lu"/impressions n'est **pas** effacé (les articles déjà
lus restent lus). Reset par utilisateur.

**Acceptance** : depuis Profile, l'utilisateur peut réinitialiser sa reco après confirmation ;
le feed/scoring repart d'un état neutre ; tests sur le service de purge ; docs `DATA_MODEL.md` /
`API_SPEC.md` mises à jour.

---

#### [x] E17-S6 — Retours round 2

Trois retours d'usage tranchés après E17-S1/S3/S4 :

1. **Coût OpenRouter replié dans « Pipeline · Last »** — plus de bloc séparé `LlmCostBlock`. Le
   coût de la fenêtre **sélectionnée** (1h/6h/24h) s'affiche en ligne dans les agrégats pipeline ;
   le même picker pilote tout. Backend inchangé (`/stats` renvoyait déjà les trois fenêtres).
   `formatCost` bascule en `$X.XX` au-dessus de 1 $ (les centimes restent pour les fractions
   réelles) — un coût de 2 $ lit « $2.00 » et non « 200.00 ¢ ». La capture du coût est exacte
   (`cost_usd` = `total_cost` OpenRouter, en USD).
2. **Recherche Explore** — la recherche **n'a jamais dépendu des filtres** (score/source) : `ILIKE`
   sur titre + résumé de tous les articles enrichis. Les onglets + barre de filtres sont désormais
   masqués **dès le 1er caractère** (`typing`), plus seulement à partir de `MIN_SEARCH_CHARS`. Le
   champ de recherche est **réinitialisé au navigate** (bottom-nav), **sauf** au retour d'un article
   ouvert (snapshot conservé uniquement via `openingArticleRef`).
3. **Compteurs d'articles par source** — `GET /sources` renvoie `article_count_total` +
   `article_count_24h` (une requête groupée, `created_at` pour la fenêtre 24h), affichés sur la
   page Manage Sources pour les sources actives **et** en pause.

> Conso Railway (suite E17-S4) : pas de levier utile côté Postgres — Railway facture l'usage réel,
> le PG est petit au repos (~0,4 / 4,9 GB de volume), aucune RAM à « réserver » à réduire. Le gros
> poste (modèle d'embedding du worker) est déjà déchargé entre les runs.

**Acceptance** : coût lisible et piloté par le picker ; recherche découplée des filtres et champ
remis à zéro hors retour-article ; volumétrie par source visible ; tests (`test_sources_service`,
`test_explore_search`) verts ; `API_SPEC.md` à jour. ✅

---

## EPIC 18 — Open source launch (juin 2026)

**Objectif** : rendre le repo présentable pour une publication open source — README à jour et
juste, vrai déploiement Railway en **1-click**, clarification du statut du dev-log interne, et
captures d'écran réelles de l'app. **Aucun changement de comportement applicatif** : doc,
packaging et assets uniquement.

**Contexte** : le code et l'archi sont prêts. Ce qui n'est pas prêt, c'est la *surface publique* :
le README décrit un état révolu (TF-IDF, « Classic mode », 8 services Railway dont des `cron-*`
qui n'existent plus), le bouton Railway pointe sur une URL de template inventée, le repo mélange
deux noms (`yourname/niouzou` vs `OuApps/niouzou`), la « Roadmap » renvoie le lecteur vers un
décision-log de 4000 lignes, et les screenshots datent.

**Décisions actées (avec le mainteneur)** :
- Repo public canonique : **`OuApps/niouzou`** (remplace toutes les occurrences `yourname/niouzou`).
- Railway : **vrai 1-click via Template** généré depuis le projet prod (dashboard, côté mainteneur) ;
  je câble tout le reste du repo.
- Périmètre : **doc + Railway + dev-log + screenshots** (pas de fichiers de gouvernance
  CONTRIBUTING/SECURITY/CoC pour ce lot).
- `EPICS.md` : **conservé** (historique de valeur) mais étiqueté **dev-log interne** ; la roadmap
  publique vit dans le README, pas ici.
- Tags `E\d+-S\d+` dans le code : **laissés tels quels** (ancres de changelog, comme des refs de
  tickets). `CLAUDE.md` à la racine : **conservé** (signal positif « contributeur-IA friendly »).

### Stories

- [x] **E18-S1** — Réécriture du README (corriger les références périmées : TF-IDF, Classic, repo, scoring)
- [x] **E18-S2** — Déploiement Railway en 1-click (vrai Template publié `railway.com/deploy/niouzou` + section réécrite, 5 services réels)
- [x] **E18-S3** — Statut du dev-log interne (header EPICS + roadmap publique) + politique tags/CLAUDE.md
- [x] **E18-S4** — Captures d'écran réelles de l'app (MCP Firefox, viewport mobile, login mainteneur)
- [x] **E18-S5** — Robustesse du déploiement template (race Miniflux + advisory lock migrations concurrentes)

---

#### [x] E18-S1 — Réécriture du README

**Problème adressé** :

Le README décrit un état révolu et trompeur :
- Mentionne **TF-IDF** comme fallback de scoring (« TF-IDF works fine », « LLM or TF-IDF »,
  « run fully without AI (TF-IDF scoring) ») — or l'extraction est **LLM-only** depuis E16-S8 ;
  sans IA il n'y a plus de keywords, pas de TF-IDF.
- Parle de « **Classic mode** (the default) » — les modes sont `keyword` (défaut) / `smart`,
  `classic` n'est qu'un alias legacy.
- URL de clone `github.com/yourname/niouzou` incohérente avec les badges/bouton (`OuApps/niouzou`).
- Commentaire identique à corriger dans `.env.example` (« run fully without AI (TF-IDF scoring) »).

**Approche** :

1. Remplacer toutes les occurrences `yourname/niouzou` → `OuApps/niouzou` (clone, liens).
2. Réécrire le bloc « How the scoring works » et les bullets : double score persistant
   `keyword_score` ⊕ `smart_score`, extraction **LLM-only**, IA optionnelle = « pathway smart
   uniquement » (les embeddings sont locaux), pas de TF-IDF.
3. Corriger la note RAM/Smart Match et le tableau Configuration si nécessaire (cohérence
   `SCORING_MODE` `keyword|smart`).
4. Corriger le commentaire `.env.example`.
5. Remplacer la section « Roadmap » (lien direct vers EPICS) par une roadmap **publique concise**
   (cf. E18-S3).

**Acceptance** : aucune mention TF-IDF/Classic trompeuse dans README ni `.env.example` ; un seul
repo canonique partout ; un lecteur comprend le scoring sans ouvrir `EPICS.md`.

---

#### [x] E18-S2 — Déploiement Railway en 1-click (vrai Template)

**Problème adressé** :

La section « Deploy on Railway » est **périmée et cassée** :
- Décrit **8 services** dont `cron-fetch`, `cron-enrich`, `cron-refresh-weights` (et des
  `*.railway.toml` correspondants) qui **n'existent plus** — la prod tourne **5 services** :
  `api`, `pwa`, `miniflux`, `refresh-worker`, `Postgres` (le worker fait fetch+enrich+refresh
  nocturne en interne via APScheduler).
- Le bouton « Deploy on Railway » pointe sur `railway.app/new/template?template=…github…`, une
  **URL inventée** qui ne déploie rien.

**Approche** (le vrai 1-click Railway = un **Template publié** généré depuis le projet prod) :

1. *(repo, moi)* Auditer/nettoyer les `railway.toml` des 5 services réels pour qu'ils soient
   reproductibles et auto-suffisants ; documenter les variables requises (`JWT_SECRET` →
   `secret()` côté template, `OPENROUTER_API_KEY` optionnelle) et les références cross-service
   (le `DATABASE_URL` de Miniflux pointe sur la base `miniflux`, l'API garde la base par défaut).
2. *(dashboard, mainteneur)* Projet prod → Settings → **Generate Template from Project** →
   copier l'**URL de template stable** et me la transmettre.
3. *(repo, moi)* Pointer le bouton « Deploy on Railway » sur la vraie URL + réécrire la section
   avec le **nombre de services correct (5)** et la note sur la base `miniflux` partagée.

**Acceptance** : le bouton mène à un déploiement Railway réel ; `JWT_SECRET` auto-généré au
déploiement ; la doc décrit l'état réel (5 services, pas de `cron-*`).

**Réalisé (2026-06-18)** :
- Template généré depuis le projet prod par le mainteneur, puis **publié via le CLI** :
  `railway templates publish <id> --category Other --description … --readme-file docs/RAILWAY_TEMPLATE.md`
  (le CLI 5.15 sait publier ; en revanche la config *par-variable* — `secret()`, descriptions — reste
  composer-only). Statut **PUBLISHED**, code `d6cGnX`, slug public **`railway.com/deploy/niouzou`**.
- Bouton README pointé sur `https://railway.com/deploy/niouzou?referralCode=bGgJYu` ; section
  « Deploy on Railway » réécrite (5 services réels, base `miniflux` partagée).
- Fichier d'overview marketplace dédié `docs/RAILWAY_TEMPLATE.md` (sections imposées par Railway :
  *Deploy and Host / About Hosting / Why Deploy / Common Use Cases / Dependencies*) — garde le
  README projet propre.
- Page de déploiement vérifiée en live : **5 services** captés depuis `OuApps/niouzou`
  (api, pwa, refresh-worker) + image `miniflux/miniflux:2.1.0` + `Postgres`.

**Reste optionnel (composer dashboard, non faisable au CLI)** — pour un 1-click *zéro saisie* :
1. **Sécurité** : vérifier que `JWT_SECRET` / `OPENROUTER_API_KEY` du template ne portent **pas** les
   valeurs prod réelles (Railway exporte les *clés*, pas les valeurs — à confirmer).
2. Régler le défaut de `JWT_SECRET` (et `MINIFLUX_ADMIN_PASSWORD` le cas échéant) sur un secret
   **généré** (`${{ secret(32) }}`) pour éviter toute saisie utilisateur.

**Acceptance** : bouton → déploiement Railway réel (5 services, pas de `cron-*`) ✅. Le secret
auto-généré reste un *nice-to-have* composer (cf. ci-dessus).

---

#### [x] E18-S3 — Statut du dev-log interne + politique tags/CLAUDE.md

**Problème adressé** :

`docs/EPICS.md` (4000+ lignes, FR, logs de décision) est lié depuis le README sous « Roadmap » :
un contributeur clique et tombe sur un décision-log interne. Ça brouille la surface publique.

**Décision actée** :
- **Garder** `EPICS.md` (historique de valeur) ; ajouter un **en-tête en haut du fichier** le
  désignant comme *journal de développement interne / registre de décisions*, renvoyant vers le
  README pour la roadmap publique.
- Le README expose une **roadmap publique courte** (features livrées / à venir) au lieu du lien
  direct (recoupe E18-S1).
- Tags `E\d+-S\d+` dans le code : **laissés** (ancres de changelog ; churn git non justifié).
- `CLAUDE.md` racine : **conservé**.

**Acceptance** : la roadmap publique ne renvoie plus le lecteur vers le décision-log ; `EPICS.md`
porte un en-tête « dev-log interne » sans ambiguïté ; aucun tag epic touché dans le code.

---

#### [x] E18-S4 — Captures d'écran réelles de l'app

**Problème adressé** :

Le README affiche `docs/assets/screen_1..4.png`. Pour une publication soignée, on veut des
captures **réelles, récentes et belles** des écrans clés (feed, détail d'article, saved/explore,
keywords) sur l'app **déployée** (PWA Railway), en rendu **mobile-first**.

**Approche** :
- Piloter la PWA déployée (`https://pwa-production-98c2.up.railway.app`) via le **MCP Firefox**,
  viewport mobile (≈ 390×844).
- **Login mainteneur** : le mainteneur saisira son mot de passe au moment voulu (jamais stocké ni
  loggé). Naviguer les écrans clés et capturer chacun.
- Remplacer les `docs/assets/screen_*.png` par les nouvelles captures (mêmes chemins → README
  inchangé côté liens).

**Acceptance** : 4 captures réelles, propres et cohérentes (mêmes dimensions mobiles) dans
`docs/assets/` ; le README rend les nouvelles images.

---

#### [x] E18-S5 — Robustesse du déploiement template (race Miniflux + migrations concurrentes)

**Problème adressé** :

Un déploiement **neuf** du template publié plantait, pour **deux** raisons distinctes
(la plomberie env vars, elle, était correcte et iso-prod : api/worker → base `railway`,
miniflux → base `miniflux`, mêmes références) :
1. **Race Miniflux** : Railway n'ordonne pas le démarrage des services → Miniflux boote avant que
   le `preDeployCommand` de l'API ait créé la base `miniflux` (`database "miniflux" does not exist`),
   et abandonne (restart `ON_FAILURE` / 10 retries épuisés avant que l'API ait fini son build à froid).
2. **Migrations concurrentes** : `alembic upgrade head` (preDeploy API) échouait sur base vierge avec
   `UniqueViolationError` sur `pg_type` / `CREATE TABLE alembic_version` — **deux runs alembic en
   parallèle** (tentatives de redéploiement qui se chevauchent) qui tentent tous deux de créer
   `alembic_version`. `env.py` n'avait aucun verrou. Latent : la prod ne l'a jamais touché (base
   migrée depuis longtemps).

**Fix** :
- Miniflux : restart policy **`Always`** (composer) → boucle jusqu'à ce que la base `miniflux`
  existe, puis persiste sur le volume (définitif). **Healthcheck Path vidé dans le template** :
  test live (projet `68f187ce`) → Miniflux finissait par connecter la base (`Starting HTTP server`)
  mais la **fenêtre de healthcheck (défaut 5 min) expirait** pendant le build à froid de l'API
  → deploy FAILED (un redéploiement manuel le passait au vert). Le champ *Healthcheck Timeout*
  n'est pas exposé dans le composer → on retire le healthcheck (sans gate, `Always` traverse la
  course tout seul). Prod garde `/healthcheck` (pas de course au build à froid).
- Migrations : **advisory lock transactionnel Postgres** dans `migrations/env.py`
  (`pg_advisory_xact_lock`) en tête de la transaction alembic → un 2ᵉ run bloque jusqu'au commit du
  1ᵉʳ, puis trouve la base à head (no-op). Aucun impact quand la base est déjà migrée (prod intacte).

**Vérification** : test de course local (deux `alembic upgrade head` simultanés sur base vierge) →
**plus aucune** `UniqueViolation`, base finale à head.

**Acceptance** : un déploiement neuf du template monte les 5 services ; `env.py` verrouillé ;
`ARCHITECTURE.md` (section Railway) documente l'ordering Miniflux + la sécurité des migrations.

---

## EPIC 19 — Polish post-lancement : desktop & onboarding (juin 2026)

Trois retours après le passage open source, en testant l'app « en conditions réelles » sur
desktop et en première connexion. PWA pur — aucun changement backend.

### Stories

#### [x] E19-S1 — Largeur desktop : colonne centrée (plus de full-width)

**Problème** : l'app est mobile-first (375px) mais aucun écran ne contraint sa largeur — sur PC
tout s'étire sur toute la fenêtre, illisible. Choix retenu : une **colonne centrée ~480px** sur
**tous** les écrans (feed swipe inclus), pour garder l'expérience « téléphone » identique sur desktop.

**Fix** : contrainte globale dans `index.css` sur `#root` (`max-width: 480px ; margin-inline: auto`,
`position: relative`) + bordures latérales discrètes ≥ 520px pour délimiter la colonne. Le
`BlobBackground` (`.bg-blobs`, `position: fixed inset: 0`) reste plein écran derrière la colonne.
`BottomNav` (fixed) recadré à la même largeur (`max-width: 480px ; margin-inline: auto`) pour
s'aligner sur la colonne. Mobile (< 480px) strictement inchangé.

**Acceptance** : sur desktop tous les écrans (Feed, Explore, Saved, Keywords, Profile, Sources,
Admin, Login/Register) s'affichent en colonne centrée ~480px, blobs plein écran derrière ; mobile
identique à avant.

#### [x] E19-S2 — Uniformisation Admin : sections repliables + popups unifiés

**Problème** : l'écran Admin mélange des sections toujours dépliées (Configuration, Scoring,
Keywords) et d'autres repliables (Users, Prompts) ; et deux popups codés à la main divergent
(`DeleteUserModal` : `glass-sm`/maxWidth 360/blur 4px/zIndex 50 ; `CompactionPreviewModal` :
`glass`/maxWidth 560/zIndex 60/sans blur).

**Fix** :
- **Sections** : toutes les sections Admin passent par un composant `AdminSection` repliable, **fermées
  par défaut** (accordéon cohérent : Configuration, Scoring engine, Keywords, Users, LLM Prompts).
- **Popups** : nouveau composant partagé `components/Modal.tsx` (backdrop `fixed inset-0`,
  `rgba(0,0,0,0.6)` + blur, centré, `glass`, maxHeight 85vh, fermeture au clic backdrop / Échap).
  `DeleteUserModal` et `CompactionPreviewModal` passent par `Modal`. (`ScoreDebugSheet` reste un
  bottom sheet — pattern volontairement distinct, hors périmètre.)

**Acceptance** : les 5 sections Admin sont des accordéons fermés par défaut ; les deux popups
partagent le même habillage via `Modal` ; Échap et clic backdrop ferment.

#### [x] E19-S3 — Première connexion sans source : CTA d'ajout

**Problème** : un nouvel utilisateur sans aucune source voit le même empty-state que « plus
d'article » (« You're all caught up! ») — trompeur, aucun chemin évident vers l'ajout de source.

**Fix** : quand le deck est vide, le Feed détecte « 0 source » (`getSources`) et affiche un
empty-state dédié (« No sources yet » + bouton **Add a source** → `/sources`), au lieu du CTA
« widen the filter ». Détection paresseuse (uniquement quand le deck est vide).

**Acceptance** : compte neuf, 0 source → empty-state d'onboarding avec bouton qui redirige vers
`/sources` ; dès qu'une source existe, l'empty-state « caught up / widen filter » d'origine
revient.

#### [x] E19-S4 — Après ajout de source : déclencher le pipeline + état « fetching » live

**Problème** : une fois sa 1re source ajoutée, le nouvel utilisateur attend le prochain tick
planifié du worker (`cron_fetch_interval`, **15 min** par défaut) avant de voir le moindre article,
et entre-temps le feed vide retombe sur « You're all caught up / widen the filter » — message
trompeur (il n'a jamais eu d'article). Aucun signal de « ça arrive ».

**Fix** (déclencher + informer) :
- **Backend** — nouveau `services/worker_client.py` (`trigger_pipeline_run`, best-effort, ne lève
  jamais). `POST /sources` enchaîne un `BackgroundTask` qui kicke le worker `POST /run` **après le
  commit** de la requête (sinon le worker fetcherait avant que la source soit visible). Débouncé par
  le lock du worker (`already_running` si un run est déjà en vol) → sûr à chaque ajout. Pas de
  nouveau réglage. Le `/admin/refresh` admin-only existant est inchangé.
- **Frontend** — quand le deck est vide **et** que l'utilisateur a des sources, le Feed poll `/stats`
  (accessible à tout user : `pipeline.status` + `in_progress` done/total, `articles.pending_enrichment`,
  `articles.total` scopé aux sources du user) toutes les 6 s et **sonde silencieusement** le feed ;
  il se peuple tout seul dès que des articles arrivent (sans spinner de rechargement). Un état dédié
  `FetchingState` (« Fetching your first articles… » + progression live) remplace le CTA
  « widen filter ». Distinction : `caughtUp` = a déjà eu des articles **et** pipeline idle **et**
  rien en attente → on garde l'empty-state d'origine ; sinon → `FetchingState`.

**Vérification** : tests `test_worker_client` (started / already_running / injoignable → sentinelle,
jamais d'exception) ; `test_sources_service` vert (service inchangé) ; build/typecheck/lint PWA OK.

**Acceptance** : ajout d'une source sur compte neuf → le pipeline démarre sans attendre le tick, le
feed affiche « Fetching your first articles… » avec progression, puis charge les articles
automatiquement ; un vétéran qui a tout lu garde « caught up / widen filter ».

#### [x] E19-S5 — Backfill du flux à l'ajout (l'abonné à un flux déjà consommé voyait 0 article)

**Problème** (découvert en test prod avec `bg@gmail.com`) : E19-S4 déclenchait bien le pipeline à
l'ajout, mais le nouvel utilisateur restait **vide**. Cause **structurelle**, pas un timing :
`cron_fetch` ne tire de Miniflux que les entrées **`unread`** et les **marque `read`** après
ingestion. Miniflux est **partagé** entre tous les users niouzou (un seul user admin Miniflux) →
quand `bg` s'abonne à un flux **déjà souscrit** par un autre user (ex. Le Monde, `miniflux_feed_id=1`,
déjà 2 abonnés / 2090 articles), Miniflux renvoie `"This feed already exists"` et niouzou **réutilise
le feed id** ; or toutes ses entrées sont **déjà lues** → `cron_fetch` reçoit 0 entrée → 0 article
pour `bg`. Aucun backfill historique : le nouvel abonné n'aurait vu que du contenu publié **après**
son inscription, au prochain tick (30 min en prod).

**Fix** : à `POST /sources`, **backfiller directement** les ~30 entrées récentes du flux via le
nouveau `MinifluxClient.list_feed_entries(feed_id)` (`GET /v1/feeds/{id}/entries`, **toutes** —
lues incluses, tri `published_at desc`), insérées en `pending` pour la nouvelle source dans la même
transaction (`SourcesService._backfill_source`), avec la **même dédup `(user, url)`** que
`cron_fetch` + `ON CONFLICT (source_id, miniflux_entry_id)`. **Best-effort** : un pépin Miniflux
log et renvoie 0, sans faire échouer l'ajout. **Ne marque rien `read`** côté Miniflux (indépendant
du modèle global unread→read). Le `BackgroundTask` `trigger_pipeline_run` (E19-S4) enrichit ensuite
ces articles. Backfill appliqué aussi au chemin **revive** (re-souscription d'une source en pause).
Profondeur ~30 = constante module (`_BACKFILL_ENTRIES`), pas de nouveau réglage env.

**Limite connue** : pour un flux **totalement neuf**, Miniflux doit l'avoir poll au moins une fois
(il planifie le job à la création) — le backfill ne trouve les entrées qu'une fois ce poll passé.
Pour les flux **déjà présents** (cas dominant d'onboarding sur instance partagée), le contenu est
immédiat.

**Vérification** : `test_sources_service` — backfill insère les entrées récentes, saute les URLs déjà
détenues par le user, et un échec Miniflux ne casse pas l'ajout (3 nouveaux tests) ; 30 tests verts.

**Acceptance** : s'abonner à un flux déjà consommé par un autre user → la nouvelle source est
immédiatement peuplée de son backlog récent, puis enrichie ; pas de double si le user a déjà l'URL.

#### [x] E19-S6 — Popups : aligner sur le pattern canonique de l'app (vraie source unique)

**Problème** : E19-S2 avait unifié les **deux popups admin entre eux**, mais pas sur le standard de
confirmation **déjà établi** ailleurs (Keywords « Reset all keywords? », Profile « Reset
recommendations? »). Résultat : la popup *Delete user* détonnait — backdrop *flouté*, fond plus
sombre (`rgba(12,16,24,0.98)`), boutons 50/50 pleine largeur (radius 8, font 12), icône triangle —
là où le reste de l'app utilise un backdrop **sans flou**, panel `glass` sur `--bg-elevated`, et des
boutons **alignés à droite** (Cancel bordure `--divider` / action pleine, radius 10, font 13).

**Fix** : `components/Modal.tsx` devient la **reproduction exacte** du pattern canonique (backdrop
`rgba(0,0,0,0.6)` sans flou, panel `glass` / `--bg-elevated` / radius 20 / padding 20 / maxWidth 320
par défaut, Échap + clic backdrop). `DeleteUserModal` réécrit au format canonique (titre h3, corps,
input cohérent radius 10, boutons `justify-end`). `CompactionPreviewModal` hérite du même habillage
(maxWidth 560). Les confirmations **Keywords** et **Profile** sont **migrées sur `Modal`** (markup
identique) → plus aucune copie inline du backdrop+panel, plus de dérive possible.

**Vérification** : tsc + build + lint PWA OK (lint = baseline, bundle légèrement réduit par la
déduplication) ; `DESIGN_SYSTEM.md` documente le pattern et interdit de recoder un backdrop à la main.

**Acceptance** : les popups Delete user, Compaction, Reset keywords et Reset recommendations
partagent un habillage strictement identique via `Modal`.

#### [x] E19-S7 — Panel System : admin-only + indice de fraîcheur non-admin + purge legacy TF-IDF

**Problème** (deux défauts de conception sur le même panel).

1. **Fuite de télémétrie globale vers tous les comptes.** Le panel « System » (`Profile.tsx:302-355`,
   `SystemPanel` `:593`) est rendu pour **chaque** utilisateur connecté, contrairement à la rangée
   « Administration » juste au-dessus (`:269`) qui est gardée par `me?.is_admin`. Or il n'expose que de
   la télémétrie **globale d'instance** : santé du pipeline, file d'enrichissement, **facture
   OpenRouter** (`formatCost`, fenêtres 1h/6h/24h), et un bouton **« Run now »** qui tape
   `POST /admin/refresh` — déjà `CurrentAdmin`-gated côté serveur → **403 pour un non-admin** qui voit
   pourtant le bouton (bug UX latent). Pire, `GET /stats` n'est gardé que par `CurrentUser` : n'importe
   quel compte peut lire la facture directement via l'API. **Aucune de ces données n'est
   par-utilisateur** : un seul pipeline, une seule file, un seul compte OpenRouter. « Valeurs par user »
   n'a donc pas de sens → la bonne réponse est **admin-only**. Mais un utilisateur lambda a une attente
   légitime : « est-ce que du nouveau contenu arrive ? » → on lui garde un **indice de fraîcheur léger**
   (sans coût, sans run-now, sans internals pipeline).

2. **Code legacy TF-IDF.** Le pill `AI · Off (TF-IDF)` (`:939`), le champ `total_tfidf_fallback`
   (`schemas/stats.py:39`, `stats_service.py:104-217`) et l'heuristique `aiStatus` qui le lit
   (`:520-528`) datent d'avant **E16-S8** (enrichment **LLM-only**, plus aucun fallback TF-IDF). Le
   statut `off` ne veut plus dire « bascule TF-IDF » mais simplement « aucun enrichment IA ».

**Fix.**

- **Backend.** `GET /stats` passe sous `CurrentAdmin`. Nouveau `GET /stats/freshness` (gardé
  `CurrentUser`) renvoyant un payload **minimal** — `pipeline_status`, `pending_enrichment`,
  `last_completed_at` — assez pour dériver un état de fraîcheur, **zéro donnée sensible** (ni coût, ni
  erreurs, ni trigger). Purge de `total_tfidf_fallback` dans `schemas/stats.py` et `stats_service.py`.
- **PWA.** Le `SystemPanel` complet **et** sa rangée passent derrière `me?.is_admin` (comme
  Administration). Pour les non-admins : un **indice de fraîcheur** léger (pill / ligne unique) —
  « Nouveau contenu en route… » quand `pipeline_status === 'running'` ou `pending_enrichment > 0`,
  « Feed à jour » sinon — alimenté par `/stats/freshness`. `aiStatus` calcule `off` via `total_ai === 0`
  (plus de référence au fallback) et le pill devient `AI · Off`.

**Vérification** : tsc + build + lint PWA ; pytest (gating admin sur `/stats` → 403 non-admin, accès
`/stats/freshness` autorisé, service stats sans `total_tfidf_fallback`). Mettre à jour `API_SPEC.md`
(`/stats` devient admin, ajout `/stats/freshness`) et `ARCHITECTURE.md`/`CONVENTIONS.md` si impactés.

**Acceptance** :
- Un non-admin ne voit ni la facture OpenRouter, ni « Run now », ni les internals pipeline, et
  `GET /stats` lui renvoie **403**.
- Un non-admin voit un **indice de fraîcheur** (fetching / à jour) sur l'écran Profile.
- Plus aucune occurrence de `TF-IDF` ni `total_tfidf_fallback` dans le code.

**Implémentation** : `GET /stats` passe sous `CurrentAdmin` ; nouveau `GET /stats/freshness`
(`CurrentUser`) → `StatsService.freshness()` (pending user-scoped + dernier `pipeline_runs` global).
`EnrichmentStats.total_tfidf_fallback` supprimé du schéma + service. PWA : `SystemPanel` + rangée
derrière `me?.is_admin`, nouveau `FeedFreshnessRow` (pill « Nouveau contenu en route… / Feed à jour »
via `/stats/freshness`), `aiStatus` calcule `off` via `total_ai === 0`, pill `AI · Off`.
**Vérif** : tsc + build PWA OK, lint inchangé (baseline) ; pytest `test_endpoints` + `test_pipeline_runs`
+ `test_explore_filters` (43 passed) dont un test 403-non-admin / 200-freshness ; `API_SPEC.md` à jour.

#### [x] E19-S8 — Monitoring : panel System déplacé dans Administration, indice de fraîcheur pour tous

**Problème.** E19-S7 avait rendu le panel « System » admin-only sur le Profile et donné aux non-admins
un simple indice de fraîcheur. Mais l'incohérence restait : un admin voyait à la fois la rangée
« Administration » (qui ouvre l'écran admin) **et** un panel « System » dépliable séparé sur le même
écran Profile, alors que toute cette télémétrie d'instance appartient à l'écran d'administration. Le
souhait : **admin et non-admin voient la même chose dans le Profile** (l'indice de fraîcheur), et le
détail (santé pipeline, facture OpenRouter, « Run now ») devient un **sous-menu « Monitoring »** de
l'écran Administration.

**Fix (PWA-only, aucun changement API).**

- `Profile.tsx` : l'indice de fraîcheur (`FeedFreshnessRow`) est rendu pour **tous** les utilisateurs
  (suppression du garde `!me.is_admin`). Le bloc `SystemPanel` dépliable et tout son state
  (`stats`/`loading`/`error`/`refreshing`/`pipelineWindow`, `loadStats`, `runRefresh`, le `useEffect`
  lazy-load) sont retirés, ainsi que les helpers/composants déplacés.
- `Admin.tsx` : nouvelle `AdminSection title="Monitoring"` placée **en tête** de l'écran, alimentée par
  `MonitoringSection` (porte le state `/stats` + trigger « Run now », lazy-load au montage puisque
  l'accordéon ne monte ses enfants qu'à l'ouverture). Le `SystemPanel` complet et ses helpers
  (`aiStatus`, `formatCost`, `costForWindow`, `nextRunLabel`, `isStalled`, `ProgressBar`,
  `PipelineAggregatesBlock`, `Row`, `AiStatusPill`, `Warning`) sont déplacés tels quels depuis
  `Profile.tsx`.

**Vérif** : tsc + build PWA OK ; lint inchangé (3 erreurs baseline pré-existantes, identiques sur
`main` : `any` dans `ConfigRow`, `set-state-in-effect` + `Date.now()` du SystemPanel déplacé verbatim) ;
boot navigateur sans crash console. Aucun endpoint touché.

**Acceptance** :
- Le Profile affiche le même indice de fraîcheur pour admin et non-admin ; plus aucun panel System sur
  le Profile.
- Un admin retrouve toute la télémétrie (pipeline, facture, « Run now ») dans Administration ›
  Monitoring.

---

## EPIC 20 — Worker frugal : le modèle d'embedding hors du process always-on (juin 2026)

**Contexte / déclencheur.** En ~5 jours d'exploitation Railway, la facture a explosé. Le poste
dominant est le service **`refresh-worker`**, et E17-S4 n'a pas réglé le fond du problème.

**Diagnostic (le vrai « pourquoi »).** Le worker est un process **always-on**
(`uvicorn … refresh_worker:app` + APScheduler) qui tourne 24/7. E17-S4 a ajouté
`unload_embedding_model()` (`del` + `gc.collect()`) après chaque run en pensant rendre la RAM —
**mais ça ne la rend pas à l'OS**. Une fois `torch` + `sentence-transformers` importés et le modèle
Qwen3-0.6B (~1,2 Go) chargé **une seule fois**, le RSS du process ne redescend quasiment jamais :
l'allocateur caching de torch + les arènes glibc conservent les pages, et `torch`/`transformers`
restent importés à vie. Railway facturant l'**usage réel** (Go·h mémoire + vCPU·min), le worker paie
en continu un RSS de l'ordre de **0,5–1,5 Go, 24h/24**, alors que le modèle n'est réellement utile
que **quelques minutes par jour**.

> Preuve dans les logs prod : à 18:00 et 18:30, `fetched=0` → le run se termine en **<1 s** sans
> jamais charger le modèle. À 17:31, 39 articles → run **~4 min**. Le travail réel cumulé est de
> l'ordre de **10–30 min/jour** ; le reste du temps on paie un modèle qui dort en RAM.

**Principe de la solution.** La **seule** façon fiable de rendre la RAM à l'OS, c'est de **tuer le
process** — pas un `unload` in-process. Direction retenue (validée 2026-06-28) : **parent léger +
subprocess**.

- Le `refresh-worker` reste un petit service **always-on (~120–150 Mo, SANS jamais importer torch)**
  qui conserve ses endpoints HTTP (`/run`, `/compact/*`, `/health`) et son planning APScheduler.
- Le pipeline lourd (fetch + enrich + **embedding local**) est exécuté dans un **process enfant**
  one-shot qui importe torch, charge le modèle, fait le travail, puis **meurt** → l'OS récupère
  100 % de sa RAM (mort de process, pas `gc`).
- Au repos : pas de modèle en mémoire, pas de torch importé → RSS plancher. Pendant un run : pic bref
  (parent + enfant ~1,5 Go) le temps du run, puis retour au plancher. Gain attendu sur le worker :
  **~5–10× moins de Go·h** (et davantage les jours creux, où l'enfant ne charge même pas le modèle
  faute d'articles à enrichir).

**Alternatives écartées.** Railway **Cron Job pur** (vrai scale-to-zero, conteneur éteint entre les
runs) serait encore moins cher, mais imposait de sortir tous les endpoints HTTP du worker, un
**advisory lock Postgres**, le modèle **embarqué dans l'image** (sinon re-téléchargement de 1,2 Go
par run, conteneur neuf à chaque fois) et la perte/relocalisation du bouton « Refresh now » →
re-archi plus lourde, écartée pour l'instant. **App Sleeping** du worker : inadapté (planning
*interne* APScheduler — endormi, rien ne le réveille ; déjà tranché en E17-S4).

> Note sur les pistes initiales : **« qu'un seul thread »** agit sur le **vCPU**, pas sur la RAM
> (déjà plafonné `EMBEDDING_NUM_THREADS=3`/`OMP_NUM_THREADS=3`) → n'adresse pas le vrai problème ici,
> qui est la RAM résidente 24/7. **« Éteindre »** est obtenu via la mort du subprocess.

### Stories

#### [x] E20-S1 — Entrypoint pipeline one-shot (le process qui meurt)

**But** : un module exécutable autonome (ex. `python -m niouzou.crons.run_once`) qui exécute **un
cycle fetch + enrich complet** (extraction contenu + LLM + **embedding local**), écrit la télémétrie
dans `pipeline_runs` comme aujourd'hui, **ferme proprement le pool Postgres**, puis **`exit`**.

- Réutilise la logique de `_run_pipeline` (actuellement dans `refresh_worker.py`) — l'idée est de la
  **déplacer** dans ce one-shot, pas de la dupliquer. Le worker l'appellera via subprocess (S2).
- C'est ce process — et lui seul — qui importe torch et charge le modèle. À sa mort, la RAM
  (~1,2 Go + overhead torch) est intégralement rendue à l'OS.
- Self-reaper optionnel au démarrage de l'enfant (les `'enriching'` orphelins restent aussi couverts
  par le reaper du parent, cf. S2).
- `unload_embedding_model()` devient **inutile** (la mort du process remplace l'unload) → à retirer
  en S2.

**Acceptance** : `python -m niouzou.crons.run_once` lancé à la main fait un cycle complet, log la
télémétrie, et **se termine** (code 0) en libérant toute sa RAM ; aucun handle Postgres laissé
ouvert ; tests du one-shot (embedder injecté, jamais le vrai modèle — cf. tripwire conftest).

#### [x] E20-S2 — Parent léger : APScheduler + `/run` lancent un subprocess (jamais torch en parent)

**But** : refondre `workers/refresh_worker.py` pour que le process always-on **n'importe jamais
torch** et ne charge **jamais** le modèle. Le planning et le déclenchement manuel **spawnent**
l'entrypoint S1 comme process enfant.

- `_guarded_run` (scheduler) et `POST /run` (bouton admin) appellent
  `asyncio.create_subprocess_exec(sys.executable, "-m", "niouzou.crons.run_once", …)` au lieu
  d'exécuter le pipeline en process. L'enfant **hérite stdout/stderr** → logs visibles dans Railway ;
  la télémétrie `/stats` continue de fonctionner (l'enfant écrit `pipeline_runs` directement en DB).
- **Verrou** : le `asyncio.Lock` in-process est conservé et **tenu pendant toute la vie de
  l'enfant** (`await proc.wait()` sous le lock). Un seul enfant à la fois ; la compaction-apply (qui
  prend le même `_lock`) reste mutuellement exclusive avec le pipeline → **pas besoin d'advisory lock
  Postgres** (une seule réplique).
- **Timeout / reaping** : si l'enfant dépasse une durée max (ex. 20 min), le parent le `kill` pour ne
  pas bloquer le lock indéfiniment ; le reaper `_reaper_reset_enriching` reste au démarrage du parent.
- **Trim des imports du parent** : vérifier (test) que le module worker n'importe **transitivement
  pas** torch (le RSS plancher doit rester ~120–150 Mo). Retirer l'import et l'appel
  `unload_embedding_model`.
- Compaction (`/compact/*`) **inchangée** : reste dans le parent (LLM + DB, pas de torch).

**Acceptance** : au repos, `refresh-worker` ne charge ni torch ni modèle (RSS plancher vérifié) ;
un tick planifié et le bouton « Refresh now » déclenchent bien un cycle (via subprocess) ; un seul
cycle à la fois ; la compaction et le pipeline ne se chevauchent jamais ; après chaque run le RSS
parent revient au plancher.

#### [x] E20-S3 — Nightly refresh : même modèle d'exécution

**But** : exécuter `cron_nightly_refresh` (recompute des poids + rescore dual) **aussi** en
subprocess one-shot, pour garder le parent uniformément léger et isoler les pannes.

- Note : le nightly ne charge **pas** le modèle d'embedding (le rescore smart tourne en pgvector sur
  des embeddings déjà stockés). Le passage en subprocess est surtout une question d'**isolation** et
  d'uniformité, pas de RAM. Peut réutiliser l'entrypoint S1 avec un flag (`--nightly`) ou un second
  module — à trancher à l'implémentation.

**Acceptance** : le refresh nocturne tourne en subprocess et se termine ; `/stats` et les poids
reflètent le run ; pas de régression sur la fenêtre de rescore.

#### [ ] E20-S4 — (Durcissement) modèle embarqué dans l'image au build

**But** : pré-télécharger le snapshot HuggingFace de Qwen3-Embedding-0.6B dans une **couche de
l'image Docker** au build, pour supprimer la dépendance réseau à HF au runtime et le téléchargement
de 1,2 Go au premier run après chaque déploiement.

- Moins critique dans la variante « parent + subprocess » que dans un cron pur : le conteneur parent
  étant always-on, son **cache disque persiste** entre les spawns → le re-téléchargement n'arrive
  qu'**une fois** après un déploiement. Story de durcissement (offline-friendly, cold-start plus
  rapide), pas un bloqueur.

**Acceptance** : un conteneur fraîchement déployé enrichit sans accès réseau à HuggingFace ; le
premier run après déploiement ne re-télécharge pas le modèle.

#### [x] E20-S5 — Quick-wins complémentaires (zéro/peu de code)

**But** : capter les gains faciles en parallèle de la re-archi.

- Activer **Serverless / App Sleeping** sur `api` et `pwa` (services web → se rendorment hors trafic,
  réveil sur requête entrante). À activer via l'UI Railway (pas configurable en `railway.toml`).
- Éventuellement porter `CRON_FETCH_INTERVAL` 30 → 60 min si la fraîcheur le tolère (1 variable).
- Documenter la conso attendue avant/après dans `ARCHITECTURE.md`.

**Acceptance** : `api`/`pwa` en Serverless ; note de conso avant/après livrée ; décision intervalle
tranchée.

> **Docs à mettre à jour à l'implémentation** (pas maintenant) : `ARCHITECTURE.md` (le worker n'est
> plus un process qui enrichit en propre mais un superviseur qui spawn un one-shot ; schéma + section
> « Cron Jobs » + variables), `CONVENTIONS.md` si un pattern de subprocess est introduit. La note
> mémoire « Railway worker threading » reste valide (le cap de threads continue de s'appliquer dans
> l'enfant).

#### Follow-up implémentation (livré 2026-06-29) — le page cache, le vrai dernier kilomètre

S1–S3 livrés et déployés (commit `27f8781`). Mais le graphe Railway montrait un plancher idle
~1,25 Go, pas les ~150 Mo attendus. **Diagnostic (confirmé par inspection cgroup read-only via
`railway ssh`)** : tuer l'enfant rend bien la RAM **anonyme** (mesuré `anon` = 74 Mo, aucun process
résiduel) — la frugalité marche. Mais chaque fichier que l'enfant **mmap** reste dans le **page cache**
du cgroup après sa mort, et **Railway compte le page cache** dans sa métrique Memory. Deux gros
coupables : le **modèle** (~1,2 Go safetensors) ET les **libs de torch** (`libtorch_cpu.so` ≈ 442 Mo,
dossier `torch` 750 Mo).

**Correctif** (commits `bd37d65` puis `f2628f5`) : après chaque run, le parent (toujours sans torch)
appelle `posix_fadvise(DONTNEED)` sur le cache HF **et** le dossier `torch` (localisé via
`sysconfig`, jamais importé) → `_drop_run_page_cache()`. fadvise ne réclame que les pages **non
mappées** du défunt enfant ; les libs encore mappées du parent (uvicorn, sqlalchemy…) sont
intactes. Mécanisme vérifié sur Linux (lecture → `Cached +N` ; fadvise → `Cached −N`) et en prod
(cgroup idle retombé à **93 Mo** : `anon` 75 Mo + `file` 0). Coût : l'enfant relit modèle+libs du
disque local au run suivant (petit cold-start, déjà accepté). **Leçon réutilisable** : « tuer le
process » libère l'anonyme mais **pas** le page cache des fichiers mmap'és — sur une plateforme qui
facture le page cache, il faut l'évincer explicitement.

**Note Serverless (S5)** : `api`/`pwa` en App Sleeping (réveil sur requête) ✅. Le **worker ne peut
pas** l'être (planning APScheduler interne → endormi, rien ne le réveille). Le vrai scale-to-zero du
worker serait un **Railway Cron Job** lançant `run_once` (conteneur éteint entre runs, 0 € idle) —
mais impose le modèle embarqué dans l'image (S4, +1,2 Go) sinon re-DL à chaque run, et la perte des
endpoints `/run` + `/compact`. Écarté au profit du correctif page-cache (2026-06-29).

---

## EPIC 21 — Chat IA sur un article (bottom sheet)

**But** : depuis n'importe quel article, ouvrir une conversation avec un LLM dont le
**contexte de départ est l'article** (résumé + texte crawlé). L'utilisateur pose des
questions, obtient des précisions, ou élargit le sujet — un fil de discussion classique,
ancré sur l'article. Le placement retenu (maquettes du 2026-07-09, option A choisie par le
mainteneur) est un **bottom sheet** qui remonte du bas et laisse l'article visible,
assombri, derrière — le même geste que le `ScoreDebugSheet` déjà en place.

**Reference** : `docs/DESIGN_SYSTEM.md` (bottom sheet = pattern existant), `docs/API_SPEC.md`,
`docs/ARCHITECTURE.md` (OpenRouter, variables d'env), `docs/DATA_MODEL.md` (app_settings).

**Dépend de** : EPIC 5 (enrichment / OpenRouter), EPIC 9 (slide plein écran = point d'entrée).

### Décisions produit (v1) — tranchées par défaut, à confirmer par le mainteneur

Les trois arbitrages ouverts de la phase maquettes ont été fixés pour une v1 livrable ;
chacun est réversible sans jeter le socle :

1. **Persistance : éphémère (en mémoire côté PWA).** La conversation vit dans le state du
   composant, rien en base. Rouvrir le sheet (ou changer d'article) repart d'un fil vide.
   → Motif : zéro migration, zéro nouvelle table, endpoint sans état. La persistance DB
   (reprise du fil, historique) est explicitement une **story de suivi** (E21-S6), pas la v1.
2. **Contexte injecté : résumé exécutif ⊕ texte crawlé, tronqué.** Le *system prompt*
   combine `summary_executive` et `content` de l'article, plafonné à
   `enrichment_input_max_chars` (réutilise le knob existant, même logique que
   l'enrichissement). Fallback sur le résumé seul quand `content` est absent.
   → Motif : meilleur ancrage, moins d'hallucinations, aucune nouvelle config.
3. **Rendu : streaming SSE.** La réponse s'écrit token par token (l'effet « en train
   d'écrire » demandé). Un indicateur de frappe (3 points) précède le premier token. Le
   mode « réponse d'un bloc » (JSON simple) reste le repli si le streaming coûte trop cher
   à livrer — le contrat d'API est pensé pour dégrader proprement (cf. E21-S2).

### Contraintes d'architecture à respecter

- **Le chat est un appel live depuis le service `api` (uvicorn), pas le worker.** Or
  `services/openrouter_client.py` est **synchrone** et pensé pour le batch d'enrichissement
  (worker). Le chat a besoin d'un **chemin async** : soit un petit client async dédié
  (`httpx.AsyncClient` sur `/chat/completions`, `stream=True`), soit exécuter le SDK sync
  dans un threadpool. **Ne pas importer torch / embeddings** dans ce chemin — le service
  `api` doit rester léger (cf. EPIC 20).
- **Réutiliser le suivi de coût OpenRouter** (`llm_usage_log`, E10-S7) pour que le chat
  apparaisse dans « Coût OpenRouter » du panel System. En streaming, la comptabilité se fait
  sur l'événement final d'usage renvoyé par OpenRouter (ou via `/generation` en différé,
  comme l'enrichissement).
- **AI-only.** Sans clé OpenRouter, le chat est indisponible : le back renvoie une erreur
  explicite (`ai_disabled`) et le front **masque le point d'entrée** — cohérent avec les
  pins / l'écran Keywords / la compaction, déjà AI-only.

### Stories

#### [x] E21-S1 — Réglage : modèle de conversation (`chat_model`)

**But** : un modèle OpenRouter dédié au chat, distinct de celui de l'enrichissement
(le chat veut du dialogue/raisonnement ; l'enrichissement veut rapide + bon marché).

- Nouvelle clé overridable `chat_model` dans `SettingsService.OVERRIDABLE_KEYS`
  (`settings_service.py`), avec son défaut env `CHAT_MODEL` dans `config.py`. Défaut :
  reprendre `openrouter_model` si non défini (pas de régression pour les instances
  existantes), sinon `openrouter/auto`.
- Exposé par `GET /admin/config` et modifiable via `PATCH /admin/config` (champ
  `chat_model`, même validation qu'`openrouter_model`).
- Écran Admin : un `ConfigRow type="model"` (réutilise `GET /admin/models`) placé **juste
  sous** le modèle d'enrichissement, libellé « Modèle de conversation ».

**Acceptance** : `chat_model` lisible/modifiable via l'API et l'écran Admin ; défaut = modèle
d'enrichissement quand non configuré ; masqué comme les autres réglages si besoin.

#### [x] E21-S2 — Endpoint chat streaming `POST /articles/{id}/chat`

**But** : relayer une conversation vers OpenRouter, contexte article injecté.

- Router mince `articles.py` → nouveau `ChatService` (`services/chat_service.py`, toute la
  logique). Jamais d'appel LLM ou DB direct depuis le router.
- **Requête** : `{ "messages": [{ "role": "user"|"assistant", "content": "..." }] }` —
  l'historique complet du fil (v1 éphémère : le client renvoie tout à chaque tour).
- **System prompt** construit par `ChatService` : consigne (« réponds en te basant sur cet
  article, en français, concis ») ⊕ titre ⊕ `summary_executive` ⊕ `content` tronqué à
  `enrichment_input_max_chars`. Fallback résumé seul si pas de contenu.
- **Garde-fous** : l'article doit appartenir à une source de l'utilisateur (`404`/`403`
  sinon, comme `score-debug`) ; historique borné (nb de messages + longueur totale) ;
  `messages` non vide et se terminant par un tour `user`.
- **Réponse** : `text/event-stream` (SSE) — événements `token` puis un `done` final.
  Contrat pensé pour un repli non-streaming (même payload agrégé) si E21-S4 le choisit.
- **AI absente** : `409 { "error": "ai_disabled", ... }` quand pas de clé OpenRouter.
- Coût loggé dans `llm_usage_log` (réutilise E10-S7).

**Acceptance** : un POST avec un fil renvoie une réponse ancrée sur l'article en streaming ;
403/404 sur article étranger/inexistant ; 409 sans clé ; le coût remonte dans `/stats`.

#### [x] E21-S3 — Point d'entrée sur la slide article

**But** : déclencher le chat depuis l'article.

- Bouton pleine largeur **« Discuter de cet article »** dans `FeedArticleSlide.tsx`, juste
  sous « Lire l'article complet », teinté accent (dégradé orange→cyan léger pour se
  distinguer sans crier). Icône `MessageCircle` (lucide).
- Masqué quand l'IA est absente (pas de `summary_executive` **et** signal AI-off) — même
  règle que le résumé IA / les pins.
- (Optionnel, à trancher à l'implémentation) 4ᵉ bouton `MessageCircle` dans la barre
  d'action `👎 / 🔖 / 👍`. Les deux affordances peuvent coexister ; par défaut on livre
  **seulement le bouton sous le résumé** (barre d'action laissée à 3 pour ne pas la serrer).
- *Implémentation* : libellé anglais « Chat about this article » (conventions : strings EN),
  gate = `summary_executive` présent (même signal AI-only que la carte résumé — pas de
  bouton qui répondrait 409 sur une instance sans clé). Le 4ᵉ bouton de la barre d'action
  n'a **pas** été livré (barre laissée à 3).

**Acceptance** : le bouton ouvre le sheet (E21-S4) ; invisible sans IA ; conforme au
design system (radius 14, `--accent-border`, `--accent-subtle`).

#### [x] E21-S4 — Bottom sheet de conversation (composant `ArticleChatSheet`)

**But** : la surface de chat, calquée sur `ScoreDebugSheet` (bottom sheet, **pas** `Modal`).

- Nouveau composant `components/ArticleChatSheet.tsx`, monté paresseusement (comme
  `ScoreDebugSheet`) : ferme sur backdrop, Escape, swipe-down. Hauteur ~78 %,
  `border-radius: 24 24 0 0`, `--bg-elevated`, grabber en tête.
- **En-tête de contexte** : miniature + titre de l'article (line-clamp 2) + libellé
  « ✦ Contexte : l'article » + bouton fermer.
- **Fil** : bulles user (fill accent, texte `#0c1018`) / assistant (glass), scroll auto vers
  le bas à chaque token. Indicateur de frappe (3 points, anim `bob`) avant le 1er token.
- **Suggestions de départ** (pastilles) : 2-3 amorces (« Un exemple ? », « Et les
  perfs ? »…) tant que le fil est vide.
- **Composer** : champ arrondi + bouton envoi (rond, fill accent). Gestion du clavier mobile
  (le sheet reste utilisable, input visible).
- **États** : chargement (typing), streaming (texte qui s'écrit), erreur (message + retry),
  IA absente (le point d'entrée n'aurait pas dû s'afficher, mais garde défensive).
- Client API typé dans `pwa/src/api/` (lecture du flux SSE via `fetch` + `ReadableStream`),
  types dans `pwa/src/types/`.
- `BlobBackground` : le sheet est au-dessus de la slide qui le porte déjà — pas d'écran plein
  nouveau, donc rien à ajouter.

**Acceptance** : depuis un article, le sheet s'ouvre, la 1ʳᵉ réponse s'écrit en streaming
avec l'indicateur de frappe, le fil scrolle, se ferme d'un swipe et rend au feed ; l'article
reste visible derrière.

#### [x] E21-S5 — Tests

- **Back** *(livré avec S1/S2 — `tests/test_chat.py`)* : `ChatService` — construction du
  system prompt (troncature, fallback résumé seul), garde-fous (article étranger → 403,
  inexistant → 404, historique invalide → 422, IA absente → 409). OpenRouter mocké en
  respx (flux SSE simulé — jamais d'appel réseau réel). Écriture `llm_usage_log` vérifiée
  (coût lu dans le chunk d'usage in-stream, pas de lookup `/generation` différé).
- **Front** : le repo n'a **aucune infra de test front** (pas de vitest ; la CI `test-pwa`
  = eslint + `tsc -b` + build, voir `CONVENTIONS.md`). Introduire vitest juste pour cette
  story serait hors périmètre — la couverture front est donc lint + typecheck + build,
  complétée côté API par **3 tests endpoint-level** (ASGITransport + respx) qui valident le
  câblage HTTP complet : SSE 200 relayé, 422 sur fil invalide, 409 sans clé. À revisiter si
  une infra vitest arrive.

**Acceptance** : suite verte ; aucun test ne tape OpenRouter ni ne charge le modèle
d'embedding.

#### [x] E21-S8 — Monitoring des coûts chat, prompt éditable, bonus d'engagement, marqueur IA

**But** : quatre finitions demandées après la v1.

- **Coûts chat dans le monitoring** : colonne `usage` (`'enrichment'` | `'chat'`) sur
  `llm_usage_log` (migration `a1c4e7f2b9d6`, défaut `enrichment` pour l'existant). Chaque
  fenêtre de `llm_cost.windows` porte maintenant `enrichment_cost_usd` + `chat_cost_usd`
  (`cost_usd` reste le total). Le panneau System affiche « enrich $X · chat $Y » piloté par
  le même sélecteur 1h/6h/24h que le pipeline.
- **Prompt système du chat éditable** : nouvelle entrée `chat.system` dans `llm_prompts`
  (seedée par la même migration), modifiable dans Admin → LLM Prompts. Décision : seule la
  **consigne** est éditable — le code ajoute toujours titre + résumé + contenu derrière,
  une édition ne peut pas casser l'ancrage sur l'article. Fallback code si la ligne manque.
- **Bonus d'engagement** : envoyer le **premier message** d'une conversation déclenche le
  même signal monotone que « Read full article » (`read_full_article=true`, +0.5 sur les
  poids). Décision : au 1ᵉʳ message envoyé, pas à l'ouverture du sheet (ouvrir/refermer
  sans rien demander n'est pas de l'engagement). Réutilise `onMarkRead` — optimiste,
  fire-and-forget.
- **Marqueur IA** : le bouton « Chat about this article » porte le `Sparkles` accent, le
  même marqueur IA que la carte résumé.

**Acceptance** : le split enrich/chat s'affiche pour la fenêtre sélectionnée ; éditer
`chat.system` change le comportement de l'assistant au tour suivant ; le 1ᵉʳ message pose
`read_full_article=true` ; le bouton porte le marqueur. Testé : tag `usage='chat'`,
agrégats splittés, prompt DB prioritaire sur le fallback.

#### ~~E21-S6 — (Suivi, hors v1) Persistance & reprise des conversations~~ — abandonnée

**Abandonnée le 2026-07-09** — décision mainteneur : les conversations restent éphémères,
pas de besoin d'historisation. Conservée barrée comme trace de la décision (ne pas la
re-proposer).

#### [x] E21-S7 — (Bonus) Sélecteur de modèle adapté au chat : reasoning + recherche web

**But** : le sélecteur « Chat Model » de l'Admin proposait la même curation que
l'enrichissement — des caps de prix serrés (≤ $0.10/M in, ≤ $0.40/M out) pensés pour un
batch sur chaque article, qui excluaient de fait tous les modèles de reasoning. Le chat
est un usage ponctuel où la qualité de raisonnement (et l'accès à Internet) compte.

- `GET /admin/models?usage=chat` : profil de curation dédié — caps élargis
  (≤ $5/M in, ≤ $20/M out : la classe DeepSeek R1 / o4-mini / Sonnet entre, les flagships
  hors de prix restent dehors), cache séparé par profil. `usage=enrichment` (défaut)
  inchangé.
- `AdminModel` gagne deux flags lus du catalogue OpenRouter : `reasoning`
  (`supported_parameters` contient `reasoning`/`include_reasoning`) et `web_search`
  (recherche **native** : `web_search_options` ou `pricing.web_search > 0`). En curation
  chat, tri reasoning-first ; les options du sélecteur affichent « · reasoning » /
  « · web search ».
- Nouveau réglage bool `chat_web_search` (env `CHAT_WEB_SEARCH`, overridable — premier
  usage de `BOOL_KEYS` dans `SettingsService`) : quand actif, `ChatService` ajoute
  `plugins: [{"id": "web"}]` au payload OpenRouter → **recherche Internet avec n'importe
  quel modèle** (facturée à la recherche par OpenRouter). Toggle « Chat web search » dans
  l'Admin sous le Chat Model, sauvegarde au clic (pas de dance edit/confirm pour un bool).

**Acceptance** : le sélecteur chat liste des modèles reasoning au-dessus des caps
d'enrichissement avec leurs tags ; le toggle web injecte le plugin dans l'appel (vérifié
par capture du payload en test) ; l'enrichissement garde sa curation historique.

> **Docs à mettre à jour à l'implémentation** (pas maintenant) :
> `API_SPEC.md` (nouvel endpoint `POST /articles/{id}/chat`, champ `chat_model` dans
> `GET/PATCH /admin/config` et `GET /admin/models`), `DATA_MODEL.md` (clé `chat_model` dans
> `app_settings` ; tables chat **seulement** si E21-S6 est faite), `ARCHITECTURE.md`
> (variable d'env `CHAT_MODEL`, note « client OpenRouter async côté api », le chat dans la
> liste des consommateurs OpenRouter / coût), `DESIGN_SYSTEM.md` (pattern « bottom sheet de
> chat », point d'entrée sur la slide, réglage Admin « Modèle de conversation »),
> `CONVENTIONS.md` si un pattern de client SSE async est introduit.

---

## EPIC 22 — Serveur MCP + clés service account

**But** : exposer le fil Niouzou d'un utilisateur à un client MCP (Claude
Desktop, un agent, un IDE…) via un **serveur MCP** authentifié par **clé
d'API de type service account**. L'admin génère et révoque ces clés depuis
le front. Une clé agit dans le contexte de l'utilisateur qui l'a créée
(mêmes sources, mêmes scores) : le serveur MCP ne fait qu'exposer en
lecture ce que l'API REST expose déjà à cet utilisateur.

**Choix d'implémentation** : serveur bâti sur **FastMCP** du SDK MCP officiel
(`mcp` — `mcp.server.fastmcp.FastMCP`), en transport **Streamable HTTP**
*stateless* + `json_response=True`. Les outils vivent dans `niouzou/mcp_app.py`
et délèguent à `services/mcp_service.py`. Deux points d'intégration à noter :
- **Auth** : FastMCP est enveloppé dans un petit middleware ASGI
  (`ServiceAccountAuthMiddleware`) qui résout la clé service account et publie
  l'`user_id` dans un `contextvar` lu par les outils — on évite ainsi toute la
  machinerie OAuth de FastMCP pour une simple clé d'API.
- **Montage** : monté en catch-all racine (`app.mount("", …)`, ajouté en
  dernier) pour servir `/mcp` **et** `/mcp/` sans redirection 307 ; le
  middleware ne prend que ces deux chemins et 404 le reste. La protection
  DNS-rebinding de FastMCP est désactivée (elle n'autorise que localhost et
  casserait derrière un vrai domaine — la clé est la vraie barrière).
- Le `session_manager` de FastMCP tourne via `mcp_lifespan` câblé sur le
  `lifespan` de l'app FastAPI.

**Auth** : `Authorization: Bearer nzk_…`. La clé brute n'est jamais
stockée : on persiste son SHA-256 (jeton haute entropie → pas besoin de
hash lent type bcrypt) plus un `prefix` d'affichage (`nzk_` + 8 car.) pour
identifier la clé dans l'UI. Le jeton complet n'est renvoyé **qu'une fois**,
à la création.

### Stories

#### [x] E22-S1 — Modèle `service_account_keys` + migration

- Table `service_account_keys` :
  - `id` UUID PK
  - `user_id` UUID FK → `users` (ON DELETE CASCADE) — l'utilisateur dont la
    clé emprunte le contexte (= l'admin créateur)
  - `name` TEXT — libellé lisible saisi à la création
  - `prefix` TEXT — `nzk_` + 8 premiers car. base64url, pour l'affichage
  - `key_hash` TEXT UNIQUE — SHA-256 hex du jeton complet
  - `created_at`, `last_used_at` (nullable), `revoked_at` (nullable)
- Migration Alembic `service_account_keys` (revises la tête courante).

#### [x] E22-S2 — Service + endpoints admin (générer / lister / révoquer)

- Helpers purs dans `security.py` : `generate_api_key()` (`nzk_` +
  `secrets.token_urlsafe(32)`), `hash_api_key()` (SHA-256 hex),
  `api_key_prefix()`.
- `ServiceAccountService` :
  - `create(owner_id, name)` → `(row, raw_token)` (jeton en clair une fois)
  - `list_all()` → toutes les clés, plus récentes d'abord (panel admin)
  - `revoke(key_id)` → pose `revoked_at` (404 si inconnue ; idempotent si
    déjà révoquée). La ligne reste listée en « révoquée » pour l'audit.
  - `authenticate(raw_token)` → `User | None` : hash, cherche une clé non
    révoquée, met à jour `last_used_at`, renvoie l'utilisateur propriétaire.
- Endpoints admin (guardés `CurrentAdmin`) :
  - `POST /admin/mcp-keys` `{name}` → 201 `{id, name, prefix, token, …}`
  - `GET /admin/mcp-keys` → `[{id, name, prefix, last_used_at, revoked_at,
    created_at}]`
  - `DELETE /admin/mcp-keys/{id}` → 204 (révocation)

#### [x] E22-S3 — Endpoint MCP Streamable HTTP + outils

- `POST /mcp` (et `/mcp/`) — FastMCP Streamable HTTP stateless, réponses
  `application/json`, auth par clé service account. Le SDK gère le protocole
  MCP (`initialize`, `tools/list`, `tools/call`, `ping`, notifications).
- Outils FastMCP dans `mcp_app.py`, déléguant à `McpService` (lui-même
  s'appuyant sur `FeedService` / `ExploreService` et lisant le contenu article
  en direct). Outils exposés (lecture seule, contexte propriétaire de la clé) :
  - `list_feed` `{limit?}` — le fil scoré et rangé de l'utilisateur
  - `search_articles` `{query, limit?}` — recherche texte sur ses articles
  - `get_article` `{article_id}` — détail + contenu plein texte
- Toute erreur outil (article introuvable, mauvais argument) lève une
  `McpToolError` que FastMCP renvoie en résultat `tools/call` avec
  `isError: true` (pas une erreur de protocole), conformément au spec.

#### [x] E22-S4 — UI Admin (générer / lister / révoquer)

- Section `AdminSection` « MCP / Service accounts » dans `Admin.tsx` :
  - liste des clés (nom, prefix, dernière utilisation, badge « Révoquée »)
  - formulaire de création (nom) → affiche le jeton **une seule fois** dans
    un encart copiable avec avertissement « ne sera plus affiché »
  - bouton Révoquer (confirm) par clé active
  - rappel de l'URL du endpoint MCP (`<api>/mcp`) pour configurer le client
- Client API : `getMcpKeys`, `createMcpKey(name)`, `revokeMcpKey(id)`.

**Acceptance** : un admin génère une clé, la copie, configure un client MCP
avec `<api>/mcp` + `Authorization: Bearer <clé>` ; `tools/list` renvoie les
3 outils ; `list_feed` renvoie son fil ; révoquer la clé fait échouer les
appels suivants en 401. Un non-admin reçoit 403 sur les endpoints de
gestion. La clé brute n'apparaît jamais après la création.

> ⚠️ **Pivoté par l'EPIC 23** : le contexte « propriétaire de la clé »
> décrit ci-dessus a été retiré. Depuis E23-S1 le MCP a une **identité
> propre** : il interroge toute la base en lecture seule, **sans scores ni
> données utilisateur**, et l'outil `list_feed` a été remplacé. La clé reste
> la barrière d'auth ; son `user_id` n'est plus qu'un champ d'audit
> « créée par ».

## EPIC 23 — MCP à identité propre + articles Niouzou partageables (juillet 2026)

**But** : deux changements liés.

1. **Le MCP devient une identité propre**, découplée de tout utilisateur. Un
   chatbot branché sur le MCP doit pouvoir **chercher dans toute la base**
   d'articles (titre / résumé / contenu) mais **ne jamais voir les scores ni
   les données des utilisateurs**. Fini le « la clé emprunte le contexte de
   son admin » de l'EPIC 22.
2. **Les articles Niouzou deviennent partageables par lien.** Le MCP renvoie
   pour chaque article une **URL Niouzou** (`{PUBLIC_APP_URL}/article/{id}`)
   qu'un utilisateur connecté peut ouvrir dans la PWA. Ouvrir un article issu
   d'une source **non rattachée** à l'utilisateur l'**affiche en lecture
   seule, sans scoring**. Un bouton **Partager** est ajouté sur les articles.

**Pourquoi** : le MCP de l'EPIC 22 exposait le fil *personnel* d'un
utilisateur (scores compris). Ce n'est pas ce qu'on veut pour un assistant
public : on veut un accès neutre au corpus, qui pointe vers Niouzou pour la
lecture — sans fuiter la personnalisation de qui que ce soit.

### Stories

#### [x] E23-S1 — MCP : identité propre, base entière, sans scoring

- `McpService` : les outils ne prennent plus de `user_id` et interrogent
  **toute la base** des articles `enriched` :
  - `search_articles` `{query, limit?}` — recherche `ILIKE` globale sur
    titre + résumé exécutif, tous articles enrichis, plus récents d'abord.
  - `get_article` `{article_id}` — n'importe quel article enrichi + contenu
    plein texte.
  - `list_recent_articles` `{limit?}` — **remplace `list_feed`** : les
    articles enrichis les plus récents de la base, sans aucune
    personnalisation.
- Projection retournée : `id, title, niouzou_url, url (source d'origine),
  source, summary, keywords, published_at`. **Plus de champ `score`, plus de
  `user_id`, plus de feedback.**
- `mcp_app.py` : le middleware `ServiceAccountAuthMiddleware` **valide** la
  clé (401 sinon) mais ne résout plus d'utilisateur et ne publie plus de
  `contextvar` `user_id` ; le `contextvar` est supprimé. Les descriptions
  d'outils sont réécrites (plus de « the user's feed »).
- `ServiceAccountService.authenticate(raw_token)` → renvoie la
  **`ServiceAccountKey`** (clé valide non révoquée) au lieu du `User`, et
  continue de tamponner `last_used_at`. La table et le CRUD admin sont
  inchangés ; `user_id` devient un champ d'audit « créée par » (pas de
  migration).

#### [x] E23-S2 — Config `PUBLIC_APP_URL` + lien d'article

- Nouveau réglage `public_app_url` (env `PUBLIC_APP_URL`, optionnel, défaut
  `""`) — base publique de la PWA.
- Helper `niouzou_article_url(article_id)` : renvoie
  `{public_app_url}/article/{id}` si l'URL est configurée, sinon le chemin
  relatif `/article/{id}` (dégradation propre). Utilisé par les projections
  MCP (`niouzou_url`).

#### [x] E23-S3 — `GET /articles/{id}` ouvert à tout article (problème de source)

- `ArticlesService.get` : on **retire le filtre `Source.user_id ==
  user_id`** du `WHERE` — n'importe quel article existant est récupérable par
  id. Les jointures scores/feedback restent keyées sur `user_id`, donc pour
  un article **non rattaché** elles ne matchent rien → scores `NULL`,
  réaction `none` : « on l'affiche, pas de scoring ».
- `ArticleDetail` gagne `owned: bool` (la source appartient à l'appelant).
  Le front s'en sert pour n'afficher scoring/feedback que si `owned`.
- `score_debug` et le chat article restent **gardés par la propriété**
  (403 cross-user) — inchangés : pas de scoring/chat sur un article non
  rattaché.

#### [x] E23-S4 — PWA : vue article en lien profond `/article/:id`

- Nouvel écran `ArticleView` + route `/article/:id` (sous `RequireAuth`).
  Récupère l'article via un nouveau client `getArticleDetail(id)` (+ type
  `ArticleDetail`). Mise en page lecture avec `BlobBackground`.
- `owned === true` → `ScoreBadge` + actions feedback (like / dislike / save)
  réutilisant le `feedbackStore`. `owned === false` → lecture seule + note
  discrète « Cet article ne vient pas de vos sources ».
- `Login` honore `location.state.from` pour qu'un lien partagé survive à
  l'authentification (redirection vers l'article après login).

#### [x] E23-S5 — Bouton Partager

- Icône `Share2` (lucide) dans l'en-tête de `FeedArticleSlide` et dans
  `ArticleView`. Au clic : `navigator.share({ title, url })` avec l'URL
  `${window.location.origin}/article/${id}` ; fallback presse-papier
  (`navigator.clipboard`) + petit toast « Lien copié ».

#### [x] E23-S7 — Purge des clés MCP héritées

- Les clés E22 ont été émises pour le modèle « la clé agit dans le contexte de
  son créateur ». E23-S1 change ce périmètre (base entière, sans score), donc
  une clé existante donne un accès différent de celui pour lequel elle a été
  émise. Migration Alembic `c1f7a3b9e2d5` : `DELETE FROM service_account_keys`
  au déploiement → les admins régénèrent proprement sous le nouveau modèle.
- Data-only et **irréversible** (seuls les hachages étaient stockés) : le
  `downgrade` est un no-op.

#### [x] E23-S6 — Tests + docs

- `test_mcp.py` : nouvelle surface (pas de scoping user, pas de scores,
  `niouzou_url` présent, recherche globale, `list_recent_articles`).
- Backend : test `GET /articles/{id}` sur un article **non rattaché**
  (`owned=false`, scores `null`, contenu présent).
- Docs synchronisées : `API_SPEC.md` (outils MCP + `/articles/{id}` `owned`),
  `ARCHITECTURE.md` (`PUBLIC_APP_URL`), `DATA_MODEL.md` (note audit `user_id`),
  `CLAUDE.md` (liste env).

**Acceptance** : un chatbot branché sur le MCP cherche « climat » et reçoit
des articles de sources qu'aucun compte n'a forcément, **sans aucun score** ;
chaque résultat porte une `niouzou_url`. Un utilisateur connecté ouvre cette
URL : si l'article vient de ses sources il a scoring + feedback, sinon il le
lit en lecture seule. Le bouton Partager produit un lien `/article/{id}`
ouvrable par n'importe quel compte.

---

## EPIC 24 — Tags de sources & mode Loupe (juillet 2026)

**But** : permettre à un utilisateur de **séparer ses usages** de Niouzou
(veille tech, rugby, actu générale…) sans dupliquer son moteur de
personnalisation. On introduit des **tags par source** (créés à la volée) et
un **mode Loupe** : un sélecteur, sur le Feed *et* sur la Recherche, qui
active **aucun ou un seul** tag et restreint alors le flux aux sources
portant ce tag. Chaque tag peut porter son **propre seuil de pertinence**,
éditable depuis l'écran de config admin.

**Pourquoi** : le besoin réel est à la *consultation*, pas à l'apprentissage.
L'utilisateur *connaît* son intention du moment (« là je veux du rugby ») — il
lui faut un interrupteur, pas un second cerveau. Le Smart Match étant déjà
multi-modal par construction (k-NN sans centroïde, cf. EPIC 16), forker le
modèle d'apprentissage (profils/personas séparés : `keyword_weights`,
`article_relevance_scores`, `article_feedbacks` dupliqués par profil) coûterait
cher pour un gain quasi nul côté smart. La Loupe est donc une **lentille de
consultation** posée sur le flux unique : un ajout, pas une refonte, qui ne
touche à aucun des trois concepts de scoring sacrés (`salience` /
`keyword_weight` / `*_score`). Le seuil par tag apporte la vraie valeur qu'un
flux unique ne peut pas offrir : la veille tech veut de la précision (seuil
haut), l'actu veut de la découverte (seuil bas).

**Décisions structurantes**

- **Le tag est une ressource par utilisateur** (comme les sources), créée à la
  volée. Un tag ⇄ plusieurs sources ; une source ⇄ plusieurs tags
  (`source_tags`, N–N).
- **Le seuil vit sur la ligne `tags`** (`tags.threshold`, nullable → hérite du
  `SCORE_THRESHOLD` global), **pas** dans `app_settings`. Motif :
  `app_settings` est instance-plat et admin-only, alors que les tags sont
  par-user. L'écran config admin *rend* l'éditeur de seuils (comme demandé)
  mais tape sur l'API `/tags`, pas sur `/admin/config` — ça garde
  `app_settings` propre et le réglage fonctionne pour un futur user non-admin.
  → **à confirmer** (voir fin d'epic).
- **La Loupe est un état d'UI éphémère** passé en query param (`?tag=`), pas un
  réglage serveur. Sélection unique (0 ou 1 tag). Le client remet à zéro la
  pagination quand la Loupe change (comme les filtres Explore, E11).
- La Loupe ne change **que** deux choses dans la requête : (1) le sous-ensemble
  de sources, (2) le seuil effectif. Le ranking (`feed_rank`, gravité,
  `active_method`, chips de score) est **inchangé**.

### Stories

#### [ ] E24-S1 — Modèle de données : `tags` + `source_tags`

- Nouvelle table `tags` :
  ```sql
  CREATE TABLE tags (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id),
    name       TEXT NOT NULL,
    threshold  FLOAT CHECK (threshold IS NULL OR (threshold >= 0.0 AND threshold <= 1.0)),
               -- seuil de pertinence propre au tag ; NULL = hérite du SCORE_THRESHOLD global
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  CREATE UNIQUE INDEX uq_tags_user_lower_name ON tags (user_id, lower(name));
  CREATE INDEX idx_tags_user_id ON tags (user_id);
  ```
- Table de liaison N–N :
  ```sql
  CREATE TABLE source_tags (
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tag_id    UUID NOT NULL REFERENCES tags(id)    ON DELETE CASCADE,
    PRIMARY KEY (source_id, tag_id)
  );
  CREATE INDEX idx_source_tags_tag_id ON source_tags (tag_id);
  ```
- Unicité du nom **insensible à la casse** par user (`lower(name)`), pour que
  « Rugby » et « rugby » ne coexistent pas.
- Sources en soft-delete (`deleted_at`) : le `ON DELETE CASCADE` ne se
  déclenche pas sur une source désactivée (elle n'est pas supprimée en base) —
  le lien reste, sans effet puisque la source ne produit plus d'articles. Le
  cascade sert surtout au `DELETE tags/{id}` (nettoie les liens) et à une
  éventuelle purge dure de source.
- Migration Alembic (`upgrade` crée les 2 tables + index ; `downgrade` les
  drop). Modèles ORM `Tag` + association `source_tags` ; relation
  `Source.tags` / `Tag.sources`.

#### [ ] E24-S2 — API : CRUD `/tags` (+ seuil, création à la volée)

- `TagsService` (business logic) + `routers/tags.py` (thin). Tout scopé
  `user_id`.
- `GET /tags` → `{ "tags": [{ id, name, threshold, source_count }] }`,
  triés par `name`. `source_count` = nombre de sources actives portant le tag.
- `POST /tags` `{ name, threshold? }` → `201` `{ id, name, threshold,
  source_count: 0 }`. `name` *trim*, 1–40 chars. `409` si le nom existe déjà
  (insensible casse) pour ce user. `threshold` optionnel dans `[0.0, 1.0]` ou
  `null`.
- `PATCH /tags/{id}` `{ name?, threshold? }` → `200`. `threshold: null`
  explicite = revenir à l'héritage du seuil global. Renommer vers un nom
  existant → `409`. `404` si le tag n'est pas au user.
- `DELETE /tags/{id}` → `204`. Supprime le tag et ses liens (`source_tags`
  cascade) ; **aucun article n'est touché**. Si le tag supprimé était la Loupe
  active côté client, le front retombe sur « aucun tag » (`404` sur `?tag=`
  géré proprement — voir S4).
- **Création à la volée** = flux client (S6) : la combobox de tags, sur un nom
  inconnu, appelle `POST /tags` puis réassigne (S3). Pas de sur-mécanique
  serveur.

#### [ ] E24-S3 — API : assignation tags ⇄ sources

- `GET /sources` enrichi : chaque source gagne `tags: [{ id, name }]` (triés
  par `name`). Une seule requête, jointure `source_tags` → pas de N+1.
- `PUT /sources/{id}/tags` `{ tag_ids: [uuid, …] }` → **remplace** l'ensemble
  des tags de la source (set-semantics : la liste envoyée devient l'état
  complet ; liste vide = plus aucun tag). `200` renvoie la source à jour
  (même forme que `GET /sources`, entrée unique). `422` si un `tag_id` n'est
  pas au user ; `404` si la source n'est pas au user. Max 20 tags/source.
- Choix id-based (et non name-based) pour rester RESTful et découpler la
  gestion des tags (renommage/seuil via `/tags`) de leur simple rattachement.
  La sensation « à la volée » est portée par le client (S6).

#### [ ] E24-S4 — Feed : filtre Loupe (`?tag=`) + seuil par tag

- `GET /feed` gagne un query param optionnel `tag` (UUID). Absent = comportement
  actuel (flux complet). Présent :
  - **filtre sources** : ne garde que les articles dont la source porte ce tag
    (jointure `source_tags`) ;
  - **seuil effectif** : `COALESCE(min_score explicite, tag.threshold,
    SCORE_THRESHOLD global)`. Précédence : un `min_score` de requête l'emporte
    toujours ; sinon le seuil du tag ; sinon le global.
  - `422` si `tag` n'appartient pas au user (cohérent avec `source_ids` sur
    Explore, E11). Un tag inexistant/supprimé → `422` : le client retombe sur
    « aucune Loupe ».
- **Inchangé** : formule `feed_rank`, gravité, `active_method`, les deux chips
  de score, le bypass cold-start (`cold_start` root si < `COLD_START_THRESHOLD`
  feedbacks → seuil ignoré, Loupe comprise) et le bypass cold/NULL du score
  actif. Le seuil du tag ne mord donc que pour un user « chaud » sur des
  articles scorés — même sémantique que `SCORE_THRESHOLD` aujourd'hui.
- `RANDOM_SURFACE_RATE` : les articles sous le seuil *effectif du tag*
  continuent d'être tirés aléatoirement, mais **au sein du sous-ensemble
  taggé** uniquement.
- Le curseur encode déjà `feed_rank`+`id` ; le client doit **droper le curseur**
  quand la Loupe change (doc : même règle que les filtres Explore).

#### [ ] E24-S5 — Recherche & Explore : filtre Loupe

- `GET /explore/search` gagne le même param `tag` (UUID, optionnel) : restreint
  la recherche `ILIKE` aux articles des sources portant le tag. `422` tag
  étranger. La recherche n'applique pas de seuil de pertinence (inchangé) — le
  tag n'y fait donc que **filtrer les sources**, pas de seuil appliqué.
- Par cohérence, `GET /explore/new` et `GET /explore/history` acceptent aussi
  `tag` (combinable en `AND` avec leurs `source_ids` / `min_score` existants).
  Sur `/explore/new`, comme le feed n'y applique pas `SCORE_THRESHOLD`, le tag
  n'y fait que filtrer les sources ; le seuil du tag ne s'applique **que** sur
  `GET /feed` (le seul endroit qui gate sur le seuil).
- Note doc explicite : le **seuil** par tag ne vit que sur le Feed ; ailleurs le
  tag est un pur filtre de sources.

#### [ ] E24-S6 — PWA : tags sur l'écran Sources (création à la volée)

- Chaque carte source affiche ses tags en **chips** (couleurs du
  `DESIGN_SYSTEM.md`, pas d'improvisation). Un éditeur inline (combobox type
  « token input ») permet d'ajouter/retirer des tags :
  - saisie d'un nom existant → suggestion → rattache (`PUT
    /sources/{id}/tags`) ;
  - saisie d'un nom inconnu + validation → `POST /tags` (création à la volée)
    puis rattache ;
  - retrait d'un chip → `PUT /sources/{id}/tags` sans ce tag.
- Client API typé : `listTags`, `createTag`, `setSourceTags` ; types miroir
  (`Tag`, `Source.tags`). `BlobBackground` déjà présent sur l'écran — aucun
  nouvel écran plein.

#### [ ] E24-S7 — PWA : contrôle Loupe sur Feed + Recherche

- Un contrôle **Loupe** (icône loupe lucide `Search`/`Filter` — à cadrer avec
  le design system) en tête du Feed et de l'écran Recherche : une rangée de
  chips (ou un dropdown) listant les tags du user, **sélection unique**, plus
  un état « aucun » (défaut). Sélectionner un tag ⇒ requête avec `?tag=` ;
  désélectionner ⇒ flux complet.
- Changement de Loupe ⇒ reset pagination (drop du curseur) + refetch, comme les
  filtres Explore (E11).
- La sélection est mémorisée en `localStorage` **par écran** (Feed vs
  Recherche indépendants) pour survivre à un reload, sans persistance serveur.
  Un tag disparu (supprimé) → nettoyage silencieux (le `422` du back retombe
  sur « aucune Loupe »).
- Le chip actif affiche le nom du tag ; le seuil appliqué reste transparent
  (pas d'affichage dédié en V1).

#### [ ] E24-S8 — PWA : « Seuils par tag » dans la config admin

- Nouvelle section **« Seuils par tag »** dans l'écran de configuration admin,
  à côté de `score_threshold` / `random_surface_rate`. Liste les tags du user
  avec, par ligne : le nom + un input de seuil en **pourcentage** (0–100 %,
  parité avec le badge de score et `score_threshold`) + un bouton « hériter »
  (met `threshold = null`). Renommer / supprimer un tag est aussi accessible
  ici (réutilise `PATCH` / `DELETE /tags/{id}`).
- **Important** : cette section tape l'API `/tags` (par-user), **pas**
  `/admin/config`. `GET/PATCH /admin/config` et `app_settings` ne portent
  aucun seuil de tag — voir la décision structurante en tête d'epic. La section
  est rendue dans l'écran admin par commodité (l'admin est le user principal du
  self-host), mais l'API sous-jacente reste par-user.

#### [ ] E24-S9 — Tests + docs

- Backend : CRUD `/tags` (unicité casse-insensible, `409`, `threshold` null vs
  borné) ; `PUT /sources/{id}/tags` (set-semantics, `422` tag étranger, cap 20)
  ; `GET /feed?tag=` (filtre sources + seuil effectif + précédence `min_score`
  > tag > global ; `422` tag étranger ; bypass cold-start conservé) ;
  `GET /explore/search?tag=` (filtre pur). Un test pinne que le seuil de tag ne
  s'applique **que** sur `/feed`.
- Front : store/état de la Loupe (sélection unique, reset curseur, persistance
  localStorage), rendu des chips de tags, section « Seuils par tag ».
- Docs synchronisées :
  - `DATA_MODEL.md` — tables `tags` + `source_tags`, note soft-delete/cascade.
  - `API_SPEC.md` — endpoints `/tags`, `PUT /sources/{id}/tags`, param `tag`
    sur `/feed` + Explore, `tags[]` sur `GET /sources`.
  - `ARCHITECTURE.md` — la Loupe comme lentille de consultation (un seul modèle
    d'apprentissage, seuil par tag sur le Feed).
  - `CONVENTIONS.md` si un pattern de nommage tag/loupe est introduit.
  - `DESIGN_SYSTEM.md` — chips de tags + contrôle Loupe.

**Acceptance** : l'utilisateur ajoute le tag « Rugby » à la volée sur trois de
ses sources, lui met un seuil de 40 % dans la config admin, puis sur le Feed
active la Loupe « Rugby » : le flux ne montre plus que des articles de ces
trois sources, filtrés au seuil 40 % (au lieu du seuil global), rangés par la
même formule de gravité. Il désactive la Loupe → flux complet au seuil global.
Sur l'écran Recherche, activer « Rugby » restreint la recherche aux mêmes
sources. Aucun `keyword_weight` ni score n'est dupliqué ; basculer de Loupe est
instantané.

**Décisions à confirmer**

1. **Emplacement du seuil** : sur la ligne `tags` (retenu ici, par-user) vs
   dans `app_settings` keyé par tag (instance-plat, admin-only). Le premier est
   plus propre et multi-user-safe ; le second colle littéralement à « dans la
   config admin » mais casse dès qu'un second user crée un tag.
2. **Portée de la Loupe** : Feed + Recherche seulement (demande explicite) vs
   étendue à tout Explore (New/History) — proposé en S5 par cohérence, à
   trancher.
3. **Multi-tag plus tard ?** V1 = sélection unique (0 ou 1). Si un besoin
   « Rugby OU Tech » émerge, la liaison N–N le permet déjà côté données ; seul
   le param (`tag` → `tags[]`) et l'UI évolueraient.
