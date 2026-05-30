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
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

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
  summary_short        TEXT,                     -- 3 engaging sentences (LLM) or newspaper4k built-in
  summary_executive    TEXT,                     -- bullet-point summary (LLM only, null without AI)
  og_image_url         TEXT,                     -- scraped from article page
  published_at         TIMESTAMPTZ,
  status               TEXT NOT NULL DEFAULT 'pending',
                                                 -- pending | enriched
  enriched_at          TIMESTAMPTZ,              -- set when status → enriched
  enrichment_method    VARCHAR,                  -- 'ai' or 'tfidf'; set by cron_enrich
  enrichment_error     TEXT,                     -- captured exception when AI failed and fell back to TF-IDF; null on success
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
  article_id  UUID NOT NULL REFERENCES articles(id),
  user_id     UUID NOT NULL REFERENCES users(id),
  action      TEXT NOT NULL CHECK (action IN ('like', 'dislike', 'skip', 'save')),
              -- last action wins (upsert) — idempotent by design
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (article_id, user_id)
);

CREATE INDEX idx_feedbacks_user_id ON article_feedbacks(user_id);
```

> `save` counts as `like` for keyword_weight computation purposes.
> Tapping like × 4 = 1 like. Only the last action is stored.

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

> `like_count` and `dislike_count` are kept for:
> - the "view and edit keyword scores" UI (Should Have)
> - efficient daily recompute in cron_refresh_weights
>
> weight formula:
>   weight(term, user) = Σ salience(term, article) * feedback_value(action)
>   where feedback_value: like|save = +1, dislike = -1, skip = 0

---

## Article Lifecycle

```
created (status = pending)
  → cron_enrich runs
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