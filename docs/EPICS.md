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
| EPIC 7 | PWA polish & follow-up | EPIC 4 |
| EPIC 8 | Admin panel | EPIC 3, EPIC 4 |
| EPIC 9 | Article history | EPIC 3, EPIC 4 |
| EPIC 10 | Scaling | EPIC 5 |

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

**Goal**: Anyone can self-host Niouzou with a single `docker compose up`. Repository published on GitHub under Apache 2.0 + Commons Clause.

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
- `LICENSE` file: Apache 2.0 + Commons Clause.
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

#### [ ] E7-S26 — Full-content fetch toggle for sources (Miniflux crawler)

**Problem**: Adding a source from the PWA creates the Miniflux feed with default settings (`crawler: false`). For publishers whose RSS exposes only a teaser (Rugbyrama and similar), articles are ingested as ~200-char snippets instead of full content. E7-S22 confirmed that enabling Miniflux's `crawler: true` per-feed retrieves the full article HTML for these sources, but the option is reachable today only via the Miniflux admin UI.

**Multi-user caveat**: A Miniflux feed is shared across all Niouzou users subscribed to the same URL (`sources.miniflux_feed_id` is not unique per user — see `api/niouzou/models/source.py`). The `crawler` flag lives on a shared resource, so any toggle by one user is visible to every other subscriber. Strategy: **last-write-wins, with a clear UI warning**. No per-user override (would require duplicating feeds in Miniflux, which it refuses).

**Changes**:

*API*:

- Extend `MinifluxClient.create_feed()` (`api/niouzou/services/miniflux_client.py`) with an optional `crawler: bool = False` passed through to `POST /v1/feeds`.
- Add `MinifluxClient.update_feed(feed_id, *, crawler: bool)` wrapping `PUT /v1/feeds/{id}`.
- Add `fetch_full_content: bool = False` to the `POST /sources` request body, plumbed through `SourcesService` into `create_feed(crawler=…)`.
- Add `PATCH /sources/{id}` accepting `{ "fetch_full_content": bool }`, which calls `update_feed`. The Niouzou-side `Source` row is unchanged; the state lives entirely on the Miniflux feed.
- Surface `fetch_full_content` (read from Miniflux's `crawler` field) in `GET /sources` so the PWA can render the current state.

*PWA*:

- "Add a source" form: checkbox **"Récupérer l'article complet"** with helper text "Recommandé pour les sites où le flux RSS ne contient qu'un résumé.". Unchecked by default.
- Source detail or list screen: same toggle for existing sources, with a small warning **"Ce réglage s'applique à tous les utilisateurs abonnés à cette source."** displayed near the toggle.
- Toggling calls `PATCH /sources/{id}`; the UI optimistically reflects the new state.

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

#### [ ] E7-S27 — System card: spacing fix + metric clarity

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

## EPIC 8 — Admin Panel

**Goal**: Introduce an admin role. Admin users can view and update runtime configuration (LLM model, API keys) from within the app — no SSH or env-var editing required after initial setup.

> Depends on EPIC 3 (auth + DB) and EPIC 4 (PWA).

### Stories

#### [ ] E8-S1 — Admin role

**API changes**:

- Add `is_admin` boolean column (default `false`, not null) to the `users` table — Alembic migration required
- The first user registered on a fresh instance is automatically promoted to admin (`is_admin = true`) if no admin exists yet
- Add a reusable FastAPI dependency `require_admin` that verifies `current_user.is_admin`; returns `403 Forbidden` otherwise
- Apply `require_admin` to all `/admin/*` routes

**Acceptance criteria**:

- A non-admin user calling any `/admin/*` endpoint receives `403`
- First registered user has `is_admin = true`; subsequent users have `is_admin = false`
- Alembic migration runs cleanly on an existing DB

---

#### [ ] E8-S2 — App config persistence layer

**Problem**: Settings like `OPENROUTER_MODEL` and API keys are currently env-var-only. Changing them requires a redeploy or container restart.

**Work**:

- Add an `app_settings` table: `key VARCHAR PK`, `value TEXT`, `updated_at TIMESTAMP`
- Add `SettingsService` with `get(key)` and `set(key, value)` methods
- At startup, `config.py` continues to read from env vars. At runtime, `SettingsService.get(key)` checks `app_settings` first and falls back to the env var — DB overrides env (allows runtime changes without restart)
- Supported overridable keys: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `MAX_KEYWORDS_PER_ARTICLE`
- When reading sensitive keys for display, mask the value: show only `sk-...` prefix + last 4 chars (e.g. `sk-...a3f9`); return `null` if unset

**Acceptance criteria**:

- After `SettingsService.set("OPENROUTER_MODEL", "gpt-4o")`, the next enrichment cron uses the new model without a restart
- Env vars remain the source of truth if no DB override exists

---

#### [ ] E8-S3 — Admin config endpoints

Add the following endpoints (all require `require_admin`):

- `GET /admin/config` — returns current effective values for all overridable keys:
  ```json
  {
    "openrouter_model": "anthropic/claude-3.5-sonnet",
    "openrouter_api_key": "sk-...a3f9",
    "max_keywords_per_article": 6
  }
  ```
  API keys are always masked in the response.

- `PATCH /admin/config` — partial update; body may contain any subset of the overridable keys:
  ```json
  { "openrouter_model": "openai/gpt-4o" }
  ```
  Returns the updated config (masked). Sending an empty string for an API key deletes the DB override (falls back to env var).

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

---

#### [ ] E8-S4 — PWA admin screen

**New route**: `/admin` — only reachable if `current_user.is_admin`.

**Profile screen changes**:

- Show an "Administration" menu item in `Profile.tsx` (below "Manage sources") only when the current user is admin — determined via a new field `is_admin` returned by `GET /me` (extend the E7-S1 response)
- Tapping "Administration" navigates to `/admin`

**Admin screen (`Admin.tsx`)**:

- Protected: redirect to `/` if user is not admin (client-side guard in addition to API-level guard)
- Header: "Administration" with a back button
- Three config rows, each with a label, masked current value, and an edit button:
  - **OpenRouter API key** — masked display; edit opens an inline input (password type)
  - **OpenRouter model** — shows current model name; edit opens a searchable `<select>` (or dropdown list) populated by `GET /admin/models`. Each option displays `{name} — {input_price}$ in / {output_price}$ out per M tokens`. A loading state is shown while the model list is fetching; if the call fails (no API key, network error) the field falls back to a plain text input so the admin can still type a model ID manually.
  - **Miniflux API key** — masked display; edit opens an inline input (password type)
- Each row has a "Save" button that calls `PATCH /admin/config` with only that key; shows a success checkmark or error inline
- Unsaved changes are discarded on navigation (no dirty-state warning needed)

**Acceptance criteria**:

- Non-admin users do not see the "Administration" link on Profile and are redirected away from `/admin`
- The model dropdown is populated from `GET /admin/models`; each option shows name + input/output price
- Selecting a model from the dropdown and saving sends its `id` to `PATCH /admin/config`; the displayed value updates without a full page reload
- If `GET /admin/models` fails, the field degrades to a plain text input (no broken UI)
- API key fields never show the plaintext value fetched from the server (masked on display, only the new value typed by the user is sent)

---

#### [ ] E8-S5 — User management (listing + password reset)

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

---

#### [ ] E8-S6 — Cron consolidation: move scheduled jobs into the Refresh Worker

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
- On FastAPI `startup` event, create an `AsyncIOScheduler` and register:
  - `_guarded_run` via `CronTrigger("*/15 * * * *")` (wall-clock aligned, same as the current Railway cron) — `misfire_grace_time=300` so a restart close to the trigger doesn't skip the job. Use `CronTrigger` rather than `IntervalTrigger` so the fire times are predictable and `last_fetched_at + 15 min` (computed in E7-S27) remains a valid client-side estimate.
  - `cron_refresh_weights.run()` directly (no pipeline lock needed — it's independent) daily at 03:00 — `misfire_grace_time=3600`

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
- `CRON_FETCH_INTERVAL` (already documented, default `15`) — used by the scheduler to set the interval in minutes
- `CRON_ENRICH_AFTER_FETCH` — not needed; enrich is always chained after fetch in `_run_pipeline()`
- `CRON_REFRESH_WEIGHTS_HOUR` — optional, default `3` — UTC hour for the daily weight refresh

**Acceptance criteria**:
- After deployment, the Railway project shows 3 services: `api`, `pwa`, `refresh-worker`
- The worker logs show scheduled job fires at approximately every 15 min and once at 03:00 UTC
- `POST /admin/refresh` continues to work: returns `{"status": "started"}` or `{"status": "already_running"}` correctly
- A manual `POST /admin/refresh` during a running scheduled job returns `already_running` (the lock is shared)
- Docker Compose: `docker-compose up` starts the stack with a single `worker` service; no separate cron containers
- No regression on `cron_refresh_weights` — keyword weights are recomputed daily

**Out of scope**:
- Persistent job state (APScheduler memory scheduler is sufficient; a missed daily job on restart is acceptable)
- Exposing schedule configuration via the Admin UI (E8-S2/S3 scope)
- Per-user cron isolation

---

## EPIC 9 — Article History

**Goal**: Users can browse all articles they have already seen (any impression) in an infinite-scroll list, accessible from the main navigation. To free up the navbar slot, the Keywords screen is moved into Profile settings.

> Depends on EPIC 3 (impressions in DB) and EPIC 4 (PWA navigation).

### Stories

#### [ ] E9-S1 — `GET /history` endpoint

- Returns all articles for which the current user has an `article_impression`, sorted by `impression.created_at DESC`
- Cursor-based pagination (same pattern as `GET /feed` and `GET /saved`)
- Each item includes the article fields (title, source, og_image, summary_short, relevance_score, keywords) plus `feedback_action` (`"like"` / `"dislike"` / `"save"` / `null`) and `impressed_at`
- Filtering: optional `action` query param to filter by feedback action (`like`, `dislike`, `save`, `none`)

**Acceptance criteria**:

- Articles with no feedback appear with `feedback_action: null`
- Cursor pagination returns non-overlapping pages in stable order
- An article appears at most once (most recent impression wins if duplicates exist)

---

#### [ ] E9-S2 — History screen (`History.tsx`)

- New screen at `/history`
- Layout mirrors `Saved.tsx`: thumbnail, source, title, score pill, relative timestamp
- Add a feedback badge per row: a small coloured dot or icon indicating the action (cyan = liked, red = disliked, yellow = saved, grey = no action / skip)
- Infinite scroll: load next page on scroll-to-bottom (follow `next_cursor`)
- Filter tabs at the top: All / Liked / Disliked / Saved (maps to `action` query param)
- Tap row → navigate to `/articles/:id`
- Empty state per filter tab with a friendly message

**Acceptance criteria**:

- Filter tabs switch instantly (client-side if data already loaded, otherwise re-fetches)
- Empty state visible and consistent with the rest of the design system

---

#### [ ] E9-S3 — Navbar & routing changes

**Navbar** (`BottomNav.tsx`): replace the Keywords tab with a History tab (use a clock or history icon). The navbar now has: Feed / History / Saved / Profile.

**Keywords screen relocation**:

- Remove the `/keywords` route from React Router's main routes (keep the component — it is reused)
- Add a "Keywords" menu item in `Profile.tsx` (below "Manage sources", above "Administration" if admin) that navigates to `/keywords`
- The Keywords screen itself requires no changes

**Acceptance criteria**:

- Tapping the History tab in the navbar opens `/history`
- Keywords are still accessible via Profile → Keywords
- No broken links or dead routes after the navbar change- No broken links or dead routes after the navbar change

---

## EPIC 10 — Scaling

**Goal**: Reduce the cost and improve the quality of the AI enrichment pipeline — smarter keyword extraction, token economy, and keyword deduplication — without degrading the feed relevance.

> Depends on EPIC 5 (AI enrichment pipeline in place).

### Stories

#### [ ] E10-S1 — Keyword deduplication: merge similar keywords with existing ones

*(Migrated from E7-S18)*

**Problem**: When the LLM extracts keywords for a new article, it may produce surface forms that are semantically identical to keywords already in the database — e.g. `"Cuisiner"` or `"Faire à Manger"` when `"cuisine"` already exists. Storing these as distinct keywords fragments the user's weight signal: likes/dislikes on `"cuisine"` don't propagate to `"Cuisiner"`, so the feed degrades silently over time.

**Goal**: During keyword enrichment, before inserting new keyword rows, look up existing keywords and collapse near-duplicates onto the canonical (legacy) form already in the DB.

**Approach** (LLM-assisted, no heavy ML dependency):

1. After the scorer produces its candidate keyword list for an article, collect all **distinct** keyword strings currently in the `keyword` table.
2. Send both lists to the LLM in a single prompt: *"Given these existing keywords: `[cuisine, sport, politique, …]`, map each candidate below onto the most similar existing keyword if they are semantically equivalent (same concept, different inflection / synonym / phrasing). Return a JSON object `{candidate: existing_keyword_or_null}`."*
3. For each candidate where the LLM returns a non-null mapping, replace the candidate string with the existing keyword string before upserting into the DB.
4. Candidates with no match are inserted as new keywords as usual.

**Constraints**:

- Only applies when `OPENROUTER_API_KEY` is set; TF-IDF path is unchanged.
- The existing keyword list sent to the LLM must be capped (e.g. top 200 by frequency) to stay within token limits.
- The dedup call is separate from the extraction call — a failure must not block enrichment (log warning, proceed with raw candidates).
- Never mutate existing `keyword` rows — only remap the candidate string.

**Where to implement**: `api/niouzou/scoring/` — inside `AIKeywordScorer` or a new `KeywordDeduplicator` helper called from `ScoringPipeline`.

**Acceptance criteria**:

- Given existing keyword `"cuisine"` and a new article whose LLM extraction returns `["cuisiner", "faire à manger", "technologie"]`, after dedup the article is linked to `"cuisine"` (existing) and `"technologie"` (new).
- If the dedup LLM call fails, enrichment completes normally (no exception propagates).
- The keyword list sent to the LLM is capped and does not exceed the configured token budget.
- Unit test: mock the LLM response and assert the correct keyword strings are persisted.

---

#### [ ] E10-S2 — Token economy: exploration of cost-reduction strategies

**Goal**: Investigate and benchmark techniques to reduce the number of tokens consumed per article enrichment cycle, without significantly degrading summary quality or keyword relevance.

**Questions to answer**:

- **Prompt compression**: can the system prompt and article content be compressed (e.g. truncation strategy, stripping boilerplate HTML artefacts) to reduce input tokens by a meaningful amount without quality loss?
- **Batching**: can multiple articles be enriched in a single LLM call (one prompt, N articles)? What is the quality trade-off vs. per-article calls?
- **Caching**: are there recurring article structures or sources where prompt prefixes could be cached (OpenRouter / provider-level prompt caching)?
- **Model tiering**: can cheaper/smaller models handle keyword extraction while a more capable model handles executive summaries? What is the quality delta?
- **Selective enrichment**: should articles below a certain TF-IDF pre-score skip LLM enrichment entirely (saving tokens on low-quality content)?

**Output**: A ranked list of strategies with estimated token savings, quality impact assessment, and implementation complexity for each. Written as a design note in `docs/SCALING.md`. No code required for this story.

**Acceptance criteria**:

- `docs/SCALING.md` exists and covers at least the five strategies above.
- Each strategy has: estimated token saving (%), quality risk (low/medium/high), implementation effort (S/M/L).
- A recommended prioritisation order is included.

---

#### [ ] E10-S3 — Keyword quality: reduction and precision exploration

**Goal**: Investigate why the current keyword extraction produces noisy, redundant, or overly generic keywords, and define a strategy to improve precision and reduce the total keyword count per article.

**Questions to answer**:

- What is the current average keyword count per article, and what share are stop words, named entities (person names, place names), or overly generic terms (e.g. "article", "information")?
- Would a stricter salience threshold reduce noise without losing useful signal?
- Should named entities (persons, organisations, locations) be kept, filtered, or stored in a separate dimension from topical keywords?
- Can the LLM prompt be refined (few-shot examples, explicit exclusion rules) to produce fewer, higher-quality keywords?
- Is there a maximum useful vocabulary size for the keyword weight system before it becomes counterproductive?

**Output**: A design note appended to `docs/SCALING.md` (created in E10-S2) with findings, proposed prompt changes, and a recommended keyword quality strategy. No code required for this story.

**Acceptance criteria**:

- Findings section covers current keyword distribution (average count, noise categories).
- Proposed prompt changes are written out and ready to be tested.
- A recommended keyword count cap and salience threshold are justified with rationale.
