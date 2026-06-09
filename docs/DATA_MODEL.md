# Data Model — Niouzou

## Entity Relationship Overview

```
users
  │
  ├──< sources              (one user → many sources)
  │       │
  │       └──< articles     (one source → many articles)
  │               │
  │               ├──< article_keywords        (one article → many keywords)
  │               ├──< article_relevance_scores (one article × one user → one score)
  │               ├──< article_feedbacks        (one article × one user → one feedback)
  │               └──< article_impressions      (one article × one user → seen flag)
  │
  └──< keyword_weights      (one user → many keyword weights)
```

---

## Tables

### users
```sql
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  is_admin      BOOLEAN NOT NULL DEFAULT false,     -- first registered user auto-promoted to admin (E8-S1)
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### app_settings
```sql
CREATE TABLE app_settings (
  key           VARCHAR NOT NULL PRIMARY KEY,      -- setting key (openrouter_api_key, openrouter_model, cron_fetch_interval, cron_refresh_weights_hour, max_keywords_per_article, score_threshold)
  value         TEXT NOT NULL,                     -- setting value (overrides env var at runtime)
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

> Stores system-wide settings that override env vars at runtime (E8-S2).
> Used by cron jobs and admin endpoints to persist configuration changes.
> Sensitive keys (openrouter_api_key) are masked when returned to PWA.

---

### sources
```sql
CREATE TABLE sources (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id),
  miniflux_feed_id  INTEGER NOT NULL,           -- Miniflux internal feed ID
  url               TEXT NOT NULL,              -- RSS feed URL
  name              TEXT NOT NULL,              -- display name
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at        TIMESTAMPTZ,                -- soft-delete; null when active

  UNIQUE (user_id, miniflux_feed_id)
);
```

> Sources are per-user. Two users following the same RSS feed = two source rows.
> `miniflux_feed_id` scoped to the user's Miniflux instance.
> Deleted sources are soft-deleted (`deleted_at` set) so existing articles keep a valid FK.

---

### articles
```sql
CREATE TABLE articles (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id            UUID NOT NULL REFERENCES sources(id),
  miniflux_entry_id    INTEGER NOT NULL,         -- Miniflux entry id (unique per source)
  url                  TEXT NOT NULL,
  title                TEXT NOT NULL,
  content              TEXT,                     -- full extracted content (newspaper4k or RSS fallback)
  summary_short        TEXT,                     -- legacy: kept for already-enriched rows, never populated by new enrichments
  summary_executive    TEXT,                     -- 4-6 markdown bullet points (LLM only, null without AI)
  og_image_url         TEXT,                     -- scraped from article page
  published_at         TIMESTAMPTZ,
  status               TEXT NOT NULL DEFAULT 'pending',
                                                 -- pending | enriching | enriched
                                                 -- 'enriching' is a transient marker set by the
                                                 -- refresh worker just before per-article work begins;
                                                 -- committed in its own short transaction so /stats can
                                                 -- show in-progress counts without polling memory (E10-S1).
                                                 -- The worker's startup reaper resets stuck
                                                 -- 'enriching' rows back to 'pending' so a crash
                                                 -- mid-run is recoverable.
  enriched_at          TIMESTAMPTZ,              -- set when status → enriched
  enrichment_method    VARCHAR,                  -- 'ai' or 'tfidf'; set by cron_enrich
  enrichment_error     TEXT,                     -- captured exception when AI failed and fell back to TF-IDF; null on success
  enrichment_model     VARCHAR,                  -- E10-S2: OpenRouter model id on AI success (e.g. 'google/gemma-4-28b');
                                                 -- NULL on TF-IDF (native or fallback). Powers the score-debug bottom sheet.
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (source_id, miniflux_entry_id)          -- same entry may exist for different sources (multi-user)
);

CREATE INDEX idx_articles_source_id ON articles(source_id);
CREATE INDEX idx_articles_status ON articles(status);
CREATE INDEX idx_articles_published_at ON articles(published_at DESC);
```

---

### article_keywords
```sql
CREATE TABLE article_keywords (
  article_id  UUID NOT NULL REFERENCES articles(id),
  term        TEXT NOT NULL,
  salience    FLOAT NOT NULL CHECK (salience >= 0.0 AND salience <= 1.0),
              -- importance of this keyword within the article
              -- set once at enrichment time, never updated

  PRIMARY KEY (article_id, term)
);

CREATE INDEX idx_article_keywords_term ON article_keywords(term);
```

---

### article_relevance_scores
```sql
CREATE TABLE article_relevance_scores (
  article_id        UUID NOT NULL REFERENCES articles(id),
  user_id           UUID NOT NULL REFERENCES users(id),
  relevance_score   FLOAT NOT NULL CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0),
                    -- probability the user will enjoy this article
                    -- computed once at enrichment time, never recomputed
  scorer            VARCHAR,                     -- 'tfidf' or 'ai_keyword'; null for legacy rows
  is_cold_start     BOOLEAN NOT NULL DEFAULT FALSE,
                    -- E10-S4: true when none of the article's keywords has a row
                    -- in keyword_weights for this user. Stamped by ScoringService
                    -- at enrichment time, demoted to false nightly by
                    -- cron_refresh_weights once a feedback brings a keyword
                    -- into the user's vocab. Drives the "New" badge on the PWA
                    -- and the threshold bypass in ranked_query.

  PRIMARY KEY (article_id, user_id)
);

CREATE INDEX idx_relevance_scores_user_id ON article_relevance_scores(user_id, relevance_score DESC);
```

---

### article_impressions
```sql
CREATE TABLE article_impressions (
  article_id  UUID NOT NULL REFERENCES articles(id),
  user_id     UUID NOT NULL REFERENCES users(id),
  seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (article_id, user_id)
);

-- Used to exclude already-seen articles from the feed
CREATE INDEX idx_impressions_user_id ON article_impressions(user_id);
```

> An impression is recorded the moment an article card is shown to the user,
> regardless of whether they interact with it.
> Articles with an impression row are never re-surfaced in the feed.

---

### article_feedbacks
```sql
CREATE TABLE article_feedbacks (
  article_id          UUID NOT NULL REFERENCES articles(id),
  user_id             UUID NOT NULL REFERENCES users(id),
  reaction            VARCHAR(10) NOT NULL DEFAULT 'none'
                      CHECK (reaction IN ('like', 'dislike', 'none')),
  is_saved            BOOLEAN NOT NULL DEFAULT false,
  read_full_article   BOOLEAN NOT NULL DEFAULT false,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (article_id, user_id)
);

CREATE INDEX idx_feedbacks_user_id ON article_feedbacks(user_id);
```

> Restructured in **E9-S1** — the legacy `action` column is gone. The three
> dimensions are independent: an article can simultaneously have
> `reaction='like'`, `is_saved=true`, `read_full_article=true`.
>
> **Allowed transitions**:
>
> | Field               | Transitions | Notes |
> |---------------------|-------------|-------|
> | `reaction`          | like ⇄ dislike ⇄ none | re-tap clears back to `none` |
> | `is_saved`          | bidirectional | un-save is legal |
> | `read_full_article` | **monotone** false→true only | backend silently drops `false` payloads |
>
> **Idempotent upsert**: `POST /feedback` does a partial update — only the
> fields present in the payload are touched (`COALESCE(:val, existing)`). An
> empty payload returns `400`. See `services/feedback_service.py`.

---

### keyword_weights
```sql
CREATE TABLE keyword_weights (
  user_id              UUID NOT NULL REFERENCES users(id),
  term                 TEXT NOT NULL,
  weight               FLOAT NOT NULL DEFAULT 0.0,
                       -- learned influence of this keyword on user's feed
                       -- positive = user likes content with this keyword
                       -- negative = user dislikes content with this keyword
                       -- 0.0 = unknown (neutral, never penalizes)
  like_count           INTEGER NOT NULL DEFAULT 0,
  dislike_count        INTEGER NOT NULL DEFAULT 0,
  manually_overridden  BOOLEAN NOT NULL DEFAULT false,
                       -- when true, cron_refresh_weights skips recomputing this row
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (user_id, term)
);

CREATE INDEX idx_keyword_weights_user_id ON keyword_weights(user_id);
```

> `like_count` and `dislike_count` are kept for the Keywords UI and for the
> daily recompute. Their semantics changed in **E9-S1**:
>
> - `like_count`    = rows where `reaction='like' OR is_saved`
> - `dislike_count` = rows where `reaction='dislike'`
>
> **Weight formula (E9-S1 canonical SQL)** — applied per `(user, term)` across
> every article carrying that term:
>
> ```sql
> SUM(
>   salience(term, article) * (
>       CASE WHEN fb.reaction = 'like'    THEN  1.0
>            WHEN fb.reaction = 'dislike' THEN -1.0
>            ELSE 0 END
>     + CASE WHEN fb.is_saved          THEN 0.5 ELSE 0 END
>     + CASE WHEN fb.read_full_article THEN 0.5 ELSE 0 END
>   )
> )
> ```
>
> Per-article signal contributions: `like = +1`, `dislike = -1`, `save = +0.5`,
> `read_full_article = +0.5`. Signals accumulate: like+save+read = +2.0;
> dislike+save = -0.5 (rare but legal — user keeps it for reference yet
> disagrees with the premise).

---

### pipeline_runs
```sql
CREATE TABLE pipeline_runs (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at         TIMESTAMPTZ,                   -- null while status='running'
  status               VARCHAR NOT NULL
                       CHECK (status IN ('running', 'completed', 'failed')),
  articles_fetched     INTEGER NOT NULL DEFAULT 0,    -- count returned by cron_fetch
  articles_enriched    INTEGER NOT NULL DEFAULT 0,    -- AI + TF-IDF combined
  articles_failed      INTEGER NOT NULL DEFAULT 0,    -- per-article uncaught exceptions
  articles_in_run      INTEGER NOT NULL DEFAULT 0,    -- pending snapshot frozen at loop start
  total_duration_s     FLOAT,
  avg_s_per_article    FLOAT,                         -- total / max(1, enriched)
  error                TEXT                           -- str(exc) when status='failed'
);

CREATE INDEX ix_pipeline_runs_started_at ON pipeline_runs(started_at DESC);
```

> Global (not user-scoped) — the refresh worker is single-replica and the
> history is shared by the whole instance. One row per fetch+enrich cycle
> driven by the worker (scheduled or `POST /admin/refresh`). The PWA's
> System panel reads the most recent row via `GET /stats`. `articles_in_run`
> is captured once at the start of the enrich loop so the progress-bar
> denominator doesn't drift when a concurrent fetch ingests new pending rows.
> Added in E10-S1.

---

### compaction_runs
```sql
CREATE TABLE compaction_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  applied_at        TIMESTAMPTZ,                   -- null while status='preview' or 'rejected'
  status            VARCHAR NOT NULL
                    CHECK (status IN ('preview', 'applied', 'rejected', 'failed')),
  groups_json       JSONB NOT NULL,                -- [{"canonical": ..., "aliases": [...], "skipped_reason": ...?}]
  keywords_merged   INTEGER NOT NULL DEFAULT 0,    -- sum of len(aliases) on non-skipped groups
  error             TEXT                           -- str(exc) when status='failed'
);

CREATE INDEX ix_compaction_runs_created_at ON compaction_runs(created_at DESC);
```

> Global (not user-scoped). One row per LLM-proposed keyword merge: the
> preview is persisted before any DB rewrite so the admin can review groups
> and apply or reject them. `skipped_reason="pinned"` is annotated at apply
> time on groups that touch a `manually_overridden=true` term — those
> groups are kept in the JSON for traceability but not applied (the user's
> explicit pin wins). Added in E10-S3.

---

## Article Lifecycle

```
created (status = pending)
  → cron_fetch + refresh worker schedule the next run
  → refresh worker enrich loop:
      → status = enriching  (committed in its own short transaction so
                             /stats can surface in-progress counts)
      → content extracted
      → keywords extracted (salience set, never changes)
      → relevance_score computed per user (frozen)
      → enriched_at set
      → status = enriched
  → article surfaced in feed if:
      relevance_score > SCORE_THRESHOLD
      OR random roll < RANDOM_SURFACE_RATE
  → impression recorded when shown
  → user swipes → feedback upserted → keyword_weights updated synchronously

Crash safety: an article left in 'enriching' is reset to 'pending' by the
worker's startup reaper. A per-article exception during enrichment rolls
the article back to 'pending' inline and increments `pipeline_runs.articles_failed`.
```

---

## Feed Query (conceptual)

```sql
-- Articles to surface for a given user
SELECT
  a.id,
  a.title,
  a.summary_short,
  a.og_image_url,
  a.url,
  a.published_at,
  ars.relevance_score
FROM articles a
JOIN sources s ON s.id = a.source_id
JOIN article_relevance_scores ars ON ars.article_id = a.id
LEFT JOIN article_impressions ai ON ai.article_id = a.id AND ai.user_id = :user_id
WHERE s.user_id     = :user_id
  AND a.status      = 'enriched'
  AND ai.article_id IS NULL          -- not yet seen
  AND (
    ars.relevance_score > :threshold
    OR random() < :random_surface_rate
  )
ORDER BY ars.relevance_score DESC, a.published_at DESC
LIMIT :page_size;
```