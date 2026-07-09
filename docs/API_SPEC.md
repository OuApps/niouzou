# API Specification — Niouzou

## General

- Base URL: `/api/v1`
- All endpoints return JSON
- All protected endpoints require `Authorization: Bearer <token>`
- All data is scoped to the authenticated user
- Dates: ISO 8601 UTC strings

### Error format
```json
{
  "error": "human_readable_code",
  "message": "Description of what went wrong"
}
```

Common HTTP status codes:
- `400` — invalid input
- `401` — missing or invalid token
- `403` — forbidden (resource belongs to another user)
- `404` — resource not found
- `409` — conflict (e.g. source already exists)
- `422` — validation error
- `500` — internal server error

---

## Authentication

### POST /auth/register
Create a new user account. The **first** account registered on a fresh instance
is promoted to admin (`is_admin = true`); every account after it is a regular
user.

**Request**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response `201`**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### POST /auth/login
Authenticate and receive tokens.

**Request**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response `200`**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### POST /auth/refresh
Exchange a refresh token for a new access token.

**Request**
```json
{
  "refresh_token": "eyJ..."
}
```

**Response `200`**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## Feed

### GET /feed
Returns a paginated list of articles to swipe, ordered by `feed_rank` descending.
Only returns articles not yet seen (no impression recorded).

**Ranking formula (HN-style):**
```
feed_rank = active_score / (age_in_hours + 2) ^ FEED_GRAVITY
```
- `active_score` — `keyword_score` or `smart_score` depending on the
  instance-wide `scoring_mode` (E16-S9). A cold or NULL active score ranks
  with a synthetic `0.5` baseline.
- `age_in_hours` — hours since `published_at`
- `FEED_GRAVITY` — env var, default `1.5`. Higher = recent articles surface faster. Lower = relevance dominates.

This ensures a natural mix of highly relevant older articles and fresh recent ones.

**Query parameters**

| Param | Type | Required | Description |
|---|---|---|---|
| `cursor` | string | No | Opaque cursor from previous response. Omit for first page. |
| `limit` | integer | No | Number of articles to return. Default: `20`, max: `50`. |
| `min_score` | float | No | Per-request override of `SCORE_THRESHOLD` (0.0–1.0). |
| `start` | UUID | No | **E9-S3** — pivot the first page on this article. The article is placed at slot 0 (even if already impressed), and the remaining slots continue ranking from that article's `feed_rank`. Only honoured when `cursor` is omitted. Returns `404` if the article doesn't belong to the user or isn't enriched. |

**Response `200`**
```json
{
  "articles": [
    {
      "id": "uuid",
      "title": "Why Rust is eating C++",
      "summary_short": null,
      "summary_executive": "- Rust adoption up 40% in systems programming\n- ...",
      "og_image_url": "https://example.com/image.jpg",
      "url": "https://example.com/article",
      "source": {
        "id": "uuid",
        "name": "The Pragmatic Engineer"
      },
      "published_at": "2024-01-15T10:30:00Z",
      "keyword_score": 0.87,
      "keyword_cold_start": false,
      "smart_score": 0.91,
      "smart_cold_start": false,
      "active_method": "keyword",
      "enrichment_model": "google/gemma-4-28b",
      "keywords": ["rust", "memory safety", "c++"],
      "is_premium": false,
      "reaction": "none",
      "is_saved": false,
      "read_full_article": false
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": true,
  "cold_start": false
}
```

> `next_cursor` is null when there are no more articles.
> Cursor encodes the last article's `feed_rank` + `id` to ensure stable pagination.
> **E16-S8/S9/S10** — every row carries BOTH persisted scores. `keyword_score`
> is null when the article has no keywords (LLM unavailable at enrichment —
> keyword extraction is LLM-only); `smart_score` is null when it has no
> embedding. `active_method` (`"keyword"` | `"smart"`, per the instance-wide
> `scoring_mode`) says which score drove the threshold filter and the ranking
> for this response — the PWA highlights that chip. The legacy
> `relevance_score`/`scorer`/`is_cold_start` fields are gone.
> `enrichment_model` (E10-S2) is the OpenRouter model id used on the AI success path (e.g. `"google/gemma-4-28b"`); null when the LLM was unavailable and on pre-E10-S2 rows. Same field appears on `GET /saved` and `GET /explore/*`.
> `keyword_cold_start` (E10-S4 semantics) is per-article and per-user: `true` when none of the article's keywords has a row in the user's `keyword_weights`. `smart_cold_start` is `true` while the user has no positive feedback. A cold (or NULL) **active** score passes through `score_threshold` unconditionally and ranks as if it were `0.5`; the PWA renders `–` instead of the percentage on that chip. The keyword flag is demoted nightly by `cron_nightly_refresh` once a feedback adds a weight on any of the keywords. Distinct from the per-user `cold_start` flag below.
> `keywords` is sorted by salience desc; empty array when the article has none.
> `cold_start` (response root, distinct from `is_cold_start` per article) is `true` while the user has fewer than `COLD_START_THRESHOLD` feedbacks (default `10`) — in that mode `SCORE_THRESHOLD` (and any `min_score` override) is ignored so the feed isn't empty on day one. The PWA can use this to show a "keep swiping to personalise your feed" hint.
> **E9-S1** — `reaction`, `is_saved`, `read_full_article` reflect the user's
> feedback state on the article. Defaults (`"none"`, `false`, `false`) apply
> when no feedback row exists.

---

### POST /feed/{article_id}/impression
Mark an article as seen. Called as soon as an article card is displayed in the PWA.
Prevents the article from appearing again in the feed.

**Response `204`** — no content

---

## Feedback

### POST /feedback
Record or update user feedback on an article (**E9-S1**). Partial-update
semantics — only the fields present in the body are touched. Also triggers
a synchronous recompute of `keyword_weights` for the article's keywords.

**Request** — at least one of the three optional fields must be set:
```json
{
  "article_id": "uuid",
  "reaction": "like",
  "is_saved": true,
  "read_full_article": true
}
```

| Field | Type | Semantics |
|---|---|---|
| `reaction` | `"like"` \| `"dislike"` \| `"none"` \| omitted | omitted = unchanged. `"none"` clears an existing like/dislike. |
| `is_saved` | `bool` \| omitted | omitted = unchanged. `false` is legal (un-save). |
| `read_full_article` | `bool` \| omitted | **monotone**: `true` sticks. `false` is silently dropped (never downgrades an existing `true`). |

> All three fields independent. An article may simultaneously be liked,
> saved and read. Per E9-S1, signal contributions to keyword weight are
> `like = +1`, `dislike = -1`, `is_saved = +0.5`, `read_full_article = +0.5`
> (accumulated per article × salience).

**Response `200`** — full persisted state for the (user, article) row:
```json
{
  "article_id": "uuid",
  "reaction": "like",
  "is_saved": true,
  "read_full_article": false,
  "updated_at": "2024-01-15T10:31:00Z"
}
```

**Errors**:
- `400 Bad Request` — empty payload (all three optional fields `null`); signals
  a client bug.
- `404 Not Found` — article does not belong to one of the user's sources.

---

### POST /feedback/reset
Reset the current user's recommendation engine (**E17-S5**). Wipes the learned
signal so the feed re-learns from zero: clears like/dislike reactions
(pure-reaction rows are deleted, reactions on saved/read rows are neutralised to
`"none"`) and deletes learned `keyword_weights`. **Preserved**: saved articles
(the Saved library), `read_full_article` flags, impressions/seen state, and
pinned keywords (`manually_overridden = true`). Persisted scores are not
recomputed inline — the nightly refresh rescores within its window.

Destructive and irreversible; clients should gate it behind a confirmation.

**Request** — empty body.

**Response `200`** — counts of what was cleared:
```json
{
  "reactions_cleared": 42,
  "weights_deleted": 17
}
```

---

## Articles

### GET /articles/{id}
Returns full article details. Called when user taps to expand an article before visiting the original URL.

**Response `200`**
```json
{
  "id": "uuid",
  "title": "Why Rust is eating C++",
  "url": "https://example.com/article",
  "summary_short": null,
  "summary_executive": "- Rust adoption up 40% in systems programming\n- ...",
  "og_image_url": "https://example.com/image.jpg",
  "source": {
    "id": "uuid",
    "name": "The Pragmatic Engineer",
    "url": "https://example.com"
  },
  "published_at": "2024-01-15T10:30:00Z",
  "enriched_at": "2024-01-15T10:35:00Z",
  "keyword_score": 0.87,
  "keyword_cold_start": false,
  "smart_score": 0.91,
  "smart_cold_start": false,
  "active_method": "keyword",
  "keywords": ["rust", "memory safety", "c++"],
  "is_premium": false,
  "reaction": "like",
  "is_saved": false,
  "read_full_article": false
}
```

> `summary_executive` is null when AI enrichment is disabled. It is the
> only AI-generated summary; `summary_short` is a legacy column that stays
> on already-enriched rows but is `null` on anything enriched after
> migration `bbc2d4e5f6a7`.
> `keywords` is sorted by salience desc; empty array when the article has none.
> **E9-S1** — `reaction`, `is_saved`, `read_full_article` are top-level fields
> (previously nested under a `feedback` object). Defaults (`"none"`, `false`,
> `false`) apply when no feedback row exists.

---

### GET /articles/{id}/score-debug
**E10-S2, dual since E16-S10** — Explains how BOTH scores were computed for
the current user: the keyword section (article keywords × learned weights)
and the Smart Match section (k-NN neighbours + pinned boost) are always
returned together, whatever the active mode. Used by the score-badge bottom
sheet in the PWA. Cross-user access returns `403` (never leaks another
user's `keyword_weights`).

**Response `200`**
```json
{
  "keyword_score": 0.74,
  "keyword_cold_start": false,
  "smart_score": 0.81,
  "smart_cold_start": false,
  "active_method": "keyword",
  "enrichment_model": "google/gemma-4-28b",
  "keywords": [
    { "term": "football", "weight": 1.2 },
    { "term": "fc barcelone", "weight": 0.8 },
    { "term": "ligue des champions", "weight": null }
  ],
  "liked_neighbors": [
    { "title": "Le XV de France domine l'Irlande", "similarity": 0.81,
      "value": 1.5, "age_days": 3.2, "contribution": 1.18 }
  ],
  "disliked_neighbors": [],
  "pins": [
    { "term": "rugby", "weight": 5.0, "salience": 0.9, "contribution": 4.5 }
  ]
}
```

> `keywords` is sorted by salience desc (same order as the article keyword tags).
> `weight: null` means the user has no row in `keyword_weights` for that term yet
> — semantically zero, but the PWA renders it as a dash to distinguish "unknown
> to me" from an explicit neutral.
> `enrichment_model` is null when the LLM was unavailable at enrichment.
> `keyword_score` is null when the article has no keywords; `smart_score` is
> null when it has no embedding; both are null when the article was never
> scored for this user (rare — articles enriched before the user existed).
> `liked_neighbors` / `disliked_neighbors` (E16-S7) are the top-K feedbacked
> articles most similar to this one, per polarity.
> `contribution = similarity × |value| × decay(age_days)` — the row's share
> of S+/S−. `pins` lists the user's pinned keywords present on the article
> (`contribution = weight × salience`, added inside the sigmoid). Neighbours
> are recomputed at request time, so they may differ marginally from those
> that produced the stored score if the user feedbacked since. All three are
> empty arrays when the article has no embedding.

**Errors**
- `403 forbidden` — article exists but belongs to another user's source.
- `404 not_found` — no article with that id.

---

### POST /articles/{id}/chat
**E21-S2** — Discuss the article with the LLM. The server injects the article
(title + `summary_executive` + `content` truncated to
`enrichment_input_max_chars`) as the system prompt and relays the thread to
OpenRouter using the `chat_model` setting. **Stateless in v1** — the client
sends the whole thread on every turn; nothing is persisted server-side.

**Request**
```json
{
  "messages": [
    { "role": "user", "content": "Pourquoi la sûreté mémoire compte autant ?" },
    { "role": "assistant", "content": "En C++, ~70 % des failles…" },
    { "role": "user", "content": "Un exemple concret ?" }
  ]
}
```

Bounds (422 on violation): 1–40 messages, ≤ 4 000 chars per message,
≤ 24 000 chars total, roles `user | assistant` only, **last message must be a
`user` turn**.

**Response `200`** — `text/event-stream` (SSE):
```
event: token
data: {"delta": "Prends "}

event: token
data: {"delta": "l'exemple du…"}

event: done
data: {"model": "anthropic/claude-sonnet-5", "prompt_tokens": 812, "completion_tokens": 164}
```

A mid-stream upstream failure (OpenRouter down, key revoked…) can no longer
change the HTTP status — it surfaces as a final event instead:
```
event: error
data: {"error": "upstream_error", "message": "OpenRouter unreachable"}
```

Every completed exchange is appended to `llm_usage_log` (cost included via
OpenRouter's in-stream usage accounting) so chat spend shows up in the System
panel's OpenRouter bill.

**Errors** (regular JSON, emitted before any streaming starts)
- `403 forbidden` — article belongs to another user's source.
- `404 not_found` — no article with that id.
- `409 ai_disabled` — no OpenRouter API key configured (the chat is AI-only).
- `422 validation_error` — thread bounds violated (see above).

---

## Saved Articles

### GET /saved
Returns articles the user has saved (Watch Later). Ordered by feedback `updated_at` descending.

**Query parameters**

| Param | Type | Required | Description |
|---|---|---|---|
| `cursor` | string | No | Opaque cursor from previous response. |
| `limit` | integer | No | Default: `20`, max: `50`. |

**Response `200`**
```json
{
  "articles": [
    {
      "id": "uuid",
      "title": "Why Rust is eating C++",
      "summary_short": null,
      "summary_executive": "- Rust adoption up 40% in systems programming\n- ...",
      "og_image_url": "https://example.com/image.jpg",
      "url": "https://example.com/article",
      "source": {
        "id": "uuid",
        "name": "The Pragmatic Engineer"
      },
      "published_at": "2024-01-15T10:30:00Z",
      "keyword_score": 0.87,
      "keyword_cold_start": false,
      "smart_score": 0.91,
      "smart_cold_start": false,
      "active_method": "keyword",
      "saved_at": "2024-01-15T10:31:00Z",
      "keywords": ["rust", "memory safety", "c++"],
      "is_premium": false,
      "reaction": "none",
      "is_saved": true,
      "read_full_article": false
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": false
}
```

> Sources now filtered by `is_saved = true` (was `action = 'save'`, **E9-S1**).
> `reaction`, `is_saved`, `read_full_article` are exposed so the PWA can show
> the article's full feedback state at a glance.

---

## Explore (E9-S3)

The Explore tab has two modes: **History** (articles the user has already
impressed, newest seen first) and **New** (enriched articles the user hasn't
seen yet, gravity-ranked without the score-threshold / random-surface gates
used by the regular feed). Scrolling Explore **does not** emit impressions —
the user can scan the queue without consuming articles from their feed.

### GET /explore/history

**Query parameters**

| Param | Type | Required | Description |
|---|---|---|---|
| `cursor` | string | No | Opaque cursor; keyset on `(seen_at, id)`. |
| `limit` | integer | No | Default: `20`, max: `50`. |
| `min_score` | float | No | `0.0`–`1.0`. Default `0.0` (no filter). Articles whose **active** score (per `scoring_mode`, E16-S9) is `< min_score` are dropped unless the active cold flag is `true` or the active score is NULL. Articles without a score row are dropped when `min_score > 0`. |
| `source_ids` | UUID list | No | Repeatable query param (`?source_ids=A&source_ids=B`). Max 20 values. Each UUID must belong to the current user — an unknown / foreign UUID returns `422`. |

**Response `200`**
```json
{
  "articles": [
    {
      "id": "uuid",
      "title": "Why Rust is eating C++",
      "summary_short": null,
      "summary_executive": "- ...",
      "content": null,
      "og_image_url": "https://example.com/image.jpg",
      "url": "https://example.com/article",
      "source": { "id": "uuid", "name": "The Pragmatic Engineer" },
      "published_at": "2024-01-15T10:30:00Z",
      "keyword_score": 0.87,
      "keyword_cold_start": false,
      "smart_score": 0.91,
      "smart_cold_start": false,
      "active_method": "keyword",
      "keywords": ["rust"],
      "is_premium": false,
      "reaction": "like",
      "is_saved": true,
      "read_full_article": false,
      "seen_at": "2024-01-16T08:00:00Z"
    }
  ],
  "next_cursor": "eyJzZWVuX2F0IjoiLi4uIn0=",
  "has_more": false
}
```

> `seen_at` is the timestamp of the user's impression row, not the article's
> `published_at`. Feedback state mirrors the `is_saved` / `reaction` /
> `read_full_article` the user has set on each article.

### GET /explore/new

Same payload shape as `GET /feed` (without `cold_start`). Articles are
enriched but not yet impressed. Ranked by `feed_rank DESC` — same gravity
formula as the Feed, but `SCORE_THRESHOLD` and `RANDOM_SURFACE_RATE` are
**not** applied (the user is explicitly scanning the queue).

**Query parameters**

| Param | Type | Required | Description |
|---|---|---|---|
| `cursor` | string | No | Opaque cursor; keyset on `(feed_rank, id)`. |
| `limit` | integer | No | Default: `20`, max: `50`. |
| `min_score` | float | No | `0.0`–`1.0`. Default `0.0` (no filter). Same semantic as on `/explore/history`: filters on the active score; cold-start / NULL active scores bypass the cap (consistent with E10-S4 + E16-S9). |
| `source_ids` | UUID list | No | Repeatable query param (`?source_ids=A&source_ids=B`). Max 20 values. Each UUID must belong to the current user — an unknown / foreign UUID returns `422`. |

**Response `200`**
```json
{
  "articles": [
    {
      "id": "uuid",
      "title": "Why Rust is eating C++",
      "...": "same fields as GET /feed"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

> Tap-through pattern: the PWA navigates to `/?start=:articleId` to drop the
> user into the Feed with the chosen article as the first slide. See
> `GET /feed?start=` above for the pivot semantics.

> **E11-S1** — `min_score` and `source_ids` are independent filters. They
> combine with `AND`: `?min_score=0.5&source_ids=A` returns articles from
> source A with active score ≥ 0.5 (or cold/NULL). The cursor format is
> unchanged; the client must drop the cursor when filters change.

---

### GET /explore/search

Full-text-ish search across **all** the current user's enriched articles
(**E17-S3**) — both seen and unseen. Case-insensitive `ILIKE` on `title` +
`summary_executive`; LIKE wildcards in the query are escaped (treated as
literals). Newest first; keyset on `(COALESCE(published_at, created_at), id)`.

**Query parameters**

| Param | Type | Required | Description |
|---|---|---|---|
| `q` | string | **Yes** | Search query (1–200 chars). A trimmed query shorter than 2 chars returns an empty result set (too broad). |
| `cursor` | string | No | Opaque cursor; keyset on `(sort_ts, id)`. |
| `limit` | integer | No | Default: `20`, max: `50`. |

**Response `200`** — same article shape as `GET /feed`, plus `seen_at`
(`null` when the article hasn't been impressed yet):
```json
{
  "articles": [
    {
      "id": "uuid",
      "title": "Why Rust is eating C++",
      "...": "same fields as GET /feed",
      "seen_at": "2024-01-15T10:31:00Z"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

---

## Profile

### GET /me
Returns the authenticated user's profile plus aggregate counts.

**Response `200`**
```json
{
  "email": "user@example.com",
  "is_admin": false,
  "saved_count": 42,
  "keyword_count": 18,
  "source_count": 7,
  "scoring_mode": "keyword"
}
```

> `is_admin` is `true` for the first account registered on the instance, `false`
> for everyone after (see `POST /auth/register`). It gates the admin panel.
> `scoring_mode` (E16-S5/S9) is the instance-wide active-score selector
> (`"keyword"` | `"smart"`), read-only here — it is set via
> `PATCH /admin/config`. The Keywords screen uses it to show the
> Smart Match banner.

---

## Sources

### GET /sources
Returns all RSS sources for the authenticated user.

**Response `200`**
```json
{
  "sources": [
    {
      "id": "uuid",
      "name": "The Pragmatic Engineer",
      "url": "https://newsletter.pragmaticengineer.com/feed",
      "created_at": "2024-01-01T00:00:00Z",
      "fetch_full_content": false,
      "active": true,
      "article_count_total": 128,
      "article_count_24h": 4
    }
  ]
}
```

> `fetch_full_content` mirrors the Miniflux `crawler` flag. When `true`,
> Miniflux fetches the full article HTML instead of relying on the RSS payload.
> The flag lives on the shared Miniflux feed, so changes are visible to every
> user subscribed to the same URL.
>
> `article_count_total` / `article_count_24h` (E17-S6) count every ingested
> article for the source (status-agnostic, keyed on `created_at` for the 24h
> window). Reported for paused sources too.

---

### POST /sources
Add a new RSS source. The backend registers the feed in Miniflux and creates the source record.

**Request**
```json
{
  "url": "https://newsletter.pragmaticengineer.com/feed",
  "fetch_full_content": false
}
```

> `fetch_full_content` is optional (default `false`). When `true`, the new
> Miniflux feed is created with `crawler: true`. If the feed already exists
> (another user is subscribed), the existing feed is updated to enable the
> crawler (last-write-wins). Sending `false` never downgrades an existing
> feed — use `PATCH /sources/{id}` to disable the crawler explicitly.

**Response `201`**
```json
{
  "id": "uuid",
  "name": "The Pragmatic Engineer",
  "url": "https://newsletter.pragmaticengineer.com/feed",
  "created_at": "2024-01-15T10:00:00Z",
  "fetch_full_content": false
}
```

> The feed name is auto-discovered from the RSS feed metadata.
> Returns `409` if the source URL already exists for this user.

> **Backfill (E19-S5):** within the request, the source is seeded with the
> feed's ~30 most recent Miniflux entries (read ones included) as `pending`
> articles, with per-`(user, url)` dedup. This is what lets a subscriber to an
> already-consumed shared feed see content immediately — `cron_fetch` alone
> only ever yields *unread* entries, which a prior subscriber has already
> consumed. Best-effort: a Miniflux failure logs and inserts nothing rather
> than failing the `201`.

> **Side effect (E19-S4):** after the source is committed, the API kicks the
> refresh-worker's fetch+enrich pipeline (`POST /run`) as a fire-and-forget
> background task so a brand-new user doesn't wait for the next scheduled tick.
> Best-effort — a worker that's down or already running never affects the
> `201` response. The PWA feed polls `GET /stats` and self-populates when the
> first articles land.

---

### PATCH /sources/{id}
Update the `fetch_full_content` flag on a source. The change is applied to
the underlying Miniflux feed and therefore affects every user subscribed to
the same URL — the PWA surfaces this warning before the toggle.

**Request**
```json
{
  "fetch_full_content": true
}
```

**Response `200`** — same shape as `POST /sources`.

> Returns `404` if the source does not belong to the authenticated user.

---

### DELETE /sources/{id}
Remove a source. Does not delete already-collected articles.

**Response `204`** — no content

---

## Keywords

### GET /keywords
Returns all keyword weights for the authenticated user, ordered by absolute weight descending.
Used for the "view and edit keyword scores" UI.

**Query parameters**

| Param | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | No | Default: `50`, max: `200`. |
| `cursor` | string | No | Opaque cursor for pagination. |

**Response `200`**
```json
{
  "keywords": [
    {
      "term": "rust",
      "weight": 2.4,
      "like_count": 12,
      "dislike_count": 1,
      "manually_overridden": false,
      "updated_at": "2024-01-15T10:00:00Z"
    },
    {
      "term": "php",
      "weight": -1.8,
      "like_count": 0,
      "dislike_count": 9,
      "manually_overridden": true,
      "updated_at": "2024-01-14T08:00:00Z"
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": false
}
```

---

### PATCH /keywords/{term}
Manually override the weight for a keyword and/or change its pin state.

**Request** — both fields are optional, send any subset:
```json
{
  "weight": 0.0,
  "manually_overridden": true
}
```

- Sending `weight` alone pins the keyword (`manually_overridden = true`).
- Sending `{ "manually_overridden": false }` alone clears the pin without
  touching the weight value — the next `cron_nightly_refresh` run will
  recompute it from feedback.

**Response `200`**
```json
{
  "term": "rust",
  "weight": 0.0,
  "like_count": 12,
  "dislike_count": 1,
  "manually_overridden": true,
  "updated_at": "2024-01-15T11:00:00Z"
}
```

> Manual overrides are preserved by `cron_nightly_refresh` —
> the cron skips recomputing weights when `manually_overridden = true`.

---

### DELETE /keywords
Delete **all** keyword weights for the authenticated user. Hard delete, irreversible.

**Response `204`** — no content

---

## System

### GET /stats
**Admin only (E19-S7)** — returns `403` for non-admin users. The payload is
global instance telemetry (pipeline health, enrichment queue, OpenRouter
bill); non-admins use [`GET /stats/freshness`](#get-statsfreshness) instead.

System and AI-enrichment health. `articles`, `sources`, `keywords`, and
`enrichment` are scoped to the admin's own sources. The `pipeline` and
`llm_cost` blocks are **global** — the refresh worker is single-replica and
the `pipeline_runs` / `llm_usage_log` history is shared across the instance.

**Query params**

| Name | Type | Default | Description |
|---|---|---|---|
| `pipeline_window` | `"1h" \| "6h" \| "24h"` | `"6h"` | Lookback for the `pipeline.aggregates` block (E10-S5). Any other value returns `422` — the closed set keeps the value out of the SQL `interval` literal. |

**Response `200`**
```json
{
  "cron_fetch_interval_minutes": 15,
  "score_threshold": 0.6,
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
    "manually_overridden": 3,
    "distinct_keyword_count": 312,
    "last_compact_at": "2026-05-30T10:00:00Z",
    "pending_compaction_id": null
  },
  "enrichment": {
    "last_enriched_at": "2026-05-27T14:10:00Z",
    "total_ai": 1456,
    "total_tfidf": 384,
    "last_error": "JSONDecodeError: Expecting value: line 1 column 1",
    "last_error_at": "2026-05-20T13:45:00Z"
  },
  "pipeline": {
    "status": "running",
    "started_at": "2026-05-31T14:00:00Z",
    "completed_at": null,
    "articles_fetched": 8,
    "articles_enriched": 7,
    "articles_failed": 1,
    "total_duration_s": null,
    "avg_s_per_article": null,
    "error": null,
    "in_progress": { "done": 8, "total": 8 },
    "aggregates": {
      "window_hours": 6,
      "runs_count": 12,
      "articles_fetched": 84,
      "articles_enriched": 79,
      "articles_failed": 5,
      "avg_s_per_article": 28.7
    }
  },
  "llm_cost": {
    "windows": [
      { "window_hours": 1, "cost_usd": 0.0042 },
      { "window_hours": 6, "cost_usd": 0.0218 },
      { "window_hours": 24, "cost_usd": 0.0871 }
    ]
  }
}
```

> `total_tfidf` counts legacy TF-IDF-enriched articles from pre-E16-S8
> instances (enrichment is LLM-only now — no fallback), kept so upgraded
> instances can still surface them.
> `last_error` / `last_error_at` are null when no enrichment error has
> happened **in the last hour**. The 1 h window prevents an old failure
> from flagging the System panel as broken indefinitely — a recurring
> error keeps getting reported on every new failed enrichment.

> `pipeline.status` is one of `"running"`, `"completed"`, `"failed"`, or
> `"never_run"` (synthetic, returned when `pipeline_runs` is empty — fresh
> install). `in_progress` is populated only while `status === "running"`:
> `done = articles_enriched + articles_failed`, `total = articles_in_run`
> (the pending snapshot frozen at the start of the enrich loop, so the
> denominator does not drift if a concurrent fetch lands new pending rows).
> `total_duration_s` and `avg_s_per_article` are set when the run finalises;
> `avg = total / max(1, articles_enriched)` per spec — the PWA suppresses
> the display when `articles_enriched === 0`. `error` is the captured
> exception string when `status === "failed"`. Added in E10-S1.

> **E10-S5** — `pipeline.aggregates` sums `pipeline_runs` over the
> `pipeline_window` (default `6h`). Only `status="completed"` rows feed
> the sums; `running` is in-flight and `failed` rows usually have zero
> duration, both would skew `avg_s_per_article`. `avg_s_per_article` is
> a **weighted** mean — `SUM(total_duration_s) / SUM(articles_enriched)`
> across the window — so a 10-article run at 30 s contributes 10× more
> than a 1-article run at 60 s. `null` when no `completed` run lands in
> the window. The picker in the System panel drives this directly: no
> client-side cache, `/stats` is cheap.

> **E10-S3** — `keywords.distinct_keyword_count` is the global number of
> distinct rows in `article_keywords.term` (instance-wide, not user-scoped).
> `keywords.last_compact_at` is the most recent `applied_at` on
> `compaction_runs`. `keywords.pending_compaction_id` is the most recent
> preview that hasn't been applied or rejected, or null. These power the
> Keywords section of the admin panel.

> **E10-S7** — `llm_cost.windows` is the global OpenRouter bill summed over
> 1h/6h/24h from `llm_usage_log`. One row is appended per successful
> enrichment chat completion (cron_enrich / refresh worker); the $ amount is
> read back via OpenRouter's `/generation` endpoint right after the
> completion and is best-effort — a lookup failure just skips that row, it
> never affects enrichment. Drives the System panel's "Coût OpenRouter"
> display, shown unconditionally (all three windows together).

> **E11-S1** — `score_threshold` is the effective `SCORE_THRESHOLD` (DB
> override else env default), a float in `[0.0, 1.0]`. The PWA reads it
> for the Explore filter bar's "≥ seuil" chip so the displayed value
> always matches the live setting; admin edits via `PATCH /admin/config`
> are reflected on the next `/stats` call.

---

### GET /stats/freshness
**Any authenticated user (E19-S7).** A deliberately minimal slice of the
System telemetry for non-admin users — no OpenRouter cost, no pipeline
errors, no run trigger. Just enough for the Profile screen to tell a regular
user whether new content is on its way.

**Response `200`**
```json
{
  "pipeline_status": "running",
  "pending_enrichment": 7,
  "last_completed_at": "2026-05-31T13:45:00Z"
}
```

> `pipeline_status` is the global worker state (`"running"` / `"completed"` /
> `"failed"` / `"never_run"`, same values as `pipeline.status` on `/stats`).
> `pending_enrichment` is scoped to **this** user's sources. `last_completed_at`
> is the global pipeline's last successful finish (null on a fresh install).
> The PWA derives a single "fetching / up to date" pill from
> `pipeline_status === "running" || pending_enrichment > 0`.

---

### POST /admin/refresh
Trigger `cron_fetch` followed by `cron_enrich` as a background task.
Concurrent runs are debounced server-side; the response is identical whether a
new run started or one was already in flight.

**Requires admin role (E8-S1)**

**Response `202`**
```json
{ "status": "started" }
```
or
```json
{ "status": "already_running" }
```

---

## Admin

### GET /admin/config
Fetch current system configuration. All fields reflect either the database
override (app_settings) or the corresponding environment variable.
Sensitive fields (API keys) are masked.

**Requires admin role (E8-S1)**

**Response `200`**
```json
{
  "openrouter_model": "openrouter/auto",
  "chat_model": "anthropic/claude-sonnet-5",
  "openrouter_api_key": "sk-...a3f9",
  "max_keywords_per_article": 25,
  "cron_fetch_interval": 15,
  "cron_nightly_refresh_hour": 3,
  "score_threshold": 0.0,
  "random_surface_rate": 0.05,
  "enrichment_input_max_chars": 2500,
  "scoring_mode": "keyword",
  "embeddings_done": 1240,
  "articles_total": 1312
}
```

> `scoring_mode` (E16-S4/S9): `"keyword"` (the default) or `"smart"` —
> selects which persisted score drives the feed. `embeddings_done` /
> `articles_total` are instance-wide counts so the admin can judge whether
> an embedding backfill (`python -m niouzou.tools.backfill_embeddings`)
> is worth running before switching.

---

### PATCH /admin/config
Update system configuration. All fields are optional; omitted fields are unchanged.
Changes persist to the database (app_settings) and take effect immediately for
the next cron run.

**Requires admin role (E8-S1)**

**Request**
```json
{
  "openrouter_model": "openrouter/auto",
  "chat_model": "anthropic/claude-sonnet-5",
  "openrouter_api_key": "sk-...",
  "max_keywords_per_article": 25,
  "cron_fetch_interval": 15,
  "cron_nightly_refresh_hour": 3,
  "score_threshold": 0.6,
  "random_surface_rate": 0.05,
  "enrichment_input_max_chars": 4000,
  "scoring_mode": "smart"
}
```

> `openrouter_api_key` accepts the full secret key (or empty string to disable AI).
> `chat_model` (E21-S1) is the OpenRouter model used by `POST /articles/{id}/chat`.
> Empty string clears the override; unset falls back to the **effective**
> `openrouter_model` (DB override included), so the chat follows the enrichment
> model until explicitly configured.
> `cron_fetch_interval` is in minutes (1–1440).
> `cron_nightly_refresh_hour` is 0–23 (UTC hour).
> `enrichment_input_max_chars` is an int in `[500, 20000]` (default `2500`); caps the combined LLM enrichment input (header + vocab + title + article excerpt). Raising it grounds summaries on more real text (fewer hallucinations) at the cost of more tokens/article; takes effect on the next pipeline run.
> `score_threshold` is a float in `[0.0, 1.0]`; takes effect on the very next `GET /feed` request (no worker restart needed). The PWA admin screen edits it as a percentage (0–100 %) for parity with the score badge; the wire format stays float.
> `random_surface_rate` is a float in `[0.0, 1.0]` — the share of sub-threshold articles randomly slipped into the feed to break the echo chamber (anti-bubble). Takes effect on the very next `GET /feed` request. Only has a visible effect when `score_threshold > 0` (with the default `0.0` every article already clears the threshold, so nothing is sub-threshold to surface). Edited as a percentage (0–100 %) in the PWA; the wire format stays float.
> `scoring_mode` (E16-S4/S9) accepts `"keyword"` or `"smart"` (`"classic"`
> is tolerated as a legacy alias of `"keyword"`). `"smart"` is refused with
> **`422 validation_error`** (explicit message) when the optional
> `embeddings` extra (sentence-transformers) is not installed or the
> `vector` Postgres extension is missing. Both scores are always computed —
> switching only changes which one filters + ranks the feed, instantly, with
> no rescore; the response returns in < 1 s.

**Response `200`** — same shape as `GET /admin/config`.

---

### GET /admin/models
Fetch the curated list of OpenRouter models available for selection.
Fetched from the OpenRouter API (once per hour), filtered by price and capability.

**Requires admin role (E8-S1)**

**Response `200`**
```json
[
  {
    "id": "openrouter/auto",
    "name": "Auto (best value)",
    "input_price_per_m": 0.0,
    "output_price_per_m": 0.0,
    "context_length": 128000
  },
  {
    "id": "anthropic/claude-3-5-sonnet",
    "name": "Claude 3.5 Sonnet",
    "input_price_per_m": 0.003,
    "output_price_per_m": 0.015,
    "context_length": 200000
  }
]
```

---

### GET /admin/users
Fetch all registered users. Includes email, admin status, and registration date.

**Requires admin role (E8-S1)**

**Response `200`**
```json
[
  {
    "id": "uuid",
    "email": "admin@example.com",
    "is_admin": true,
    "created_at": "2026-01-01T00:00:00Z"
  },
  {
    "id": "uuid",
    "email": "user@example.com",
    "is_admin": false,
    "created_at": "2026-02-15T10:00:00Z"
  }
]
```

---

### PATCH /admin/users/{id}/password
Reset a user's password to a new value.

**Requires admin role (E8-S1)**

**Request**
```json
{
  "new_password": "new-secure-password"
}
```

**Response `200`** — no content (204)

> Returns `404` if the user does not exist.

---

### POST /admin/compact-keywords/preview
**E10-S3** — Ask the refresh worker to propose semantic-equivalence groups
over the top-N most-frequent `article_keywords.term` values. The LLM runs
on the worker so uvicorn stays responsive; the API merely proxies. The
preview is persisted in `compaction_runs` (status `preview`) but **no DB
rewrite has happened yet** — the admin must follow up with apply or reject.

**Requires admin role (E8-S1)**

**Response `202`**
```json
{
  "id": "uuid",
  "groups": [
    {
      "canonical": "fc barcelone",
      "aliases": ["barça", "barcelona fc"]
    }
  ]
}
```
or, if a preview is already in flight:
```json
{ "status": "already_running" }
```
or, if AI is disabled (no OpenRouter API key):
```json
{ "status": "ai_disabled", "message": "Compaction requires an OpenRouter API key." }
```

> Groups whose canonical or aliases reference terms outside the vocab
> snapshot are filtered out server-side (defense against hallucinations).
> When that happens the response can legitimately return an empty `groups`
> array — the admin UI shows "no groups to merge".

---

### POST /admin/compact-keywords/apply
Apply a preview generated by the endpoint above. Rewrites
`article_keywords` (with PK-collision pre-resolution), reruns
`cron_nightly_refresh`, and purges alias orphans from `keyword_weights`.
Held under the same lock as `POST /admin/refresh` so a pipeline run and an
apply never race.

**Requires admin role (E8-S1)**

**Request**
```json
{ "id": "uuid" }
```

**Response `202`**
```json
{ "status": "started" }
```
or
```json
{ "status": "already_running" }
```

**Errors**
- `404` — the run id is unknown.
- `409` — the run is not in `preview` state (already applied, rejected, or
  failed). The body is `{ "error": "invalid_state", "message": "..." }`.

The run id is validated *before* the 202 is returned, so a stale id from
the PWA surfaces as a real error rather than a silent background failure.

> Groups containing a `manually_overridden=true` keyword are skipped at
> apply time. They remain in `compaction_runs.groups_json` annotated with
> `skipped_reason: "pinned"` so the admin sees that a pinned weight took
> precedence.

---

### GET /admin/compact-keywords/{id}
Return a previously-generated preview so the admin can resume it. Used by
the PWA's "Reprendre la dernière analyse" affordance when
`stats.keywords.pending_compaction_id` is non-null at mount time. Reads
straight from `compaction_runs` — no LLM call.

**Requires admin role (E8-S1)**

**Response `200`**
```json
{
  "id": "uuid",
  "groups": [
    { "canonical": "fc barcelone", "aliases": ["barça", "barcelona fc"] }
  ]
}
```

**Errors**
- `404` — id unknown, or the run is no longer a preview (already applied,
  rejected, or failed). Terminal-state runs are not resumable.

---

### DELETE /admin/compact-keywords/{id}
Reject a preview without applying it. Marks the run `status='rejected'`.

**Requires admin role (E8-S1)**

**Response `204`** — no content.
