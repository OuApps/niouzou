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
Create a new user account.

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
feed_rank = relevance_score / (age_in_hours + 2) ^ FEED_GRAVITY
```
- `age_in_hours` — hours since `published_at`
- `FEED_GRAVITY` — env var, default `1.5`. Higher = recent articles surface faster. Lower = relevance dominates.

This ensures a natural mix of highly relevant older articles and fresh recent ones.

**Query parameters**

| Param | Type | Required | Description |
|---|---|---|---|
| `cursor` | string | No | Opaque cursor from previous response. Omit for first page. |
| `limit` | integer | No | Number of articles to return. Default: `20`, max: `50`. |
| `min_score` | float | No | Per-request override of `SCORE_THRESHOLD` (0.0–1.0). Used by the PWA empty state (E7-S8). |

**Response `200`**
```json
{
  "articles": [
    {
      "id": "uuid",
      "title": "Why Rust is eating C++",
      "summary_short": "Rust's memory safety guarantees...",
      "og_image_url": "https://example.com/image.jpg",
      "url": "https://example.com/article",
      "source": {
        "id": "uuid",
        "name": "The Pragmatic Engineer"
      },
      "published_at": "2024-01-15T10:30:00Z",
      "relevance_score": 0.87,
      "scorer": "ai_keyword",
      "keywords": ["rust", "memory safety", "c++"]
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": true,
  "cold_start": false
}
```

> `next_cursor` is null when there are no more articles.
> Cursor encodes the last article's `relevance_score` + `id` to ensure stable pagination.
> `scorer` is `"tfidf"` or `"ai_keyword"`; null for rows scored before E7-S7.
> `keywords` is sorted by salience desc; empty array when the article has none.
> `cold_start` is `true` while the user has fewer than `COLD_START_THRESHOLD` feedbacks (default `10`, E7-S6) — in that mode `SCORE_THRESHOLD` (and any `min_score` override) is ignored so the feed isn't empty on day one. The PWA can use this to show a "keep swiping to personalise your feed" hint.

---

### POST /feed/{article_id}/impression
Mark an article as seen. Called as soon as an article card is displayed in the PWA.
Prevents the article from appearing again in the feed.

**Response `204`** — no content

---

## Feedback

### POST /feedback
Record or update user feedback on an article. Idempotent — last action wins.
Also triggers synchronous recompute of `keyword_weights` for affected keywords.

**Request**
```json
{
  "article_id": "uuid",
  "action": "like"
}
```

`action` must be one of: `like`, `dislike`, `skip`, `save`
`save` counts as `like` for keyword_weight computation.

**Response `200`**
```json
{
  "article_id": "uuid",
  "action": "like",
  "updated_at": "2024-01-15T10:31:00Z"
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
  "summary_short": "Rust's memory safety guarantees...",
  "summary_executive": "- Rust adoption up 40% in systems programming\n- ...",
  "og_image_url": "https://example.com/image.jpg",
  "source": {
    "id": "uuid",
    "name": "The Pragmatic Engineer",
    "url": "https://example.com"
  },
  "published_at": "2024-01-15T10:30:00Z",
  "enriched_at": "2024-01-15T10:35:00Z",
  "relevance_score": 0.87,
  "feedback": {
    "action": "like",
    "updated_at": "2024-01-15T10:31:00Z"
  },
  "keywords": ["rust", "memory safety", "c++"]
}
```

> `feedback` is null if the user has not interacted with the article yet.
> `summary_executive` is null when AI enrichment is disabled.
> `keywords` is sorted by salience desc; empty array when the article has none.

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
      "summary_short": "Rust's memory safety guarantees...",
      "og_image_url": "https://example.com/image.jpg",
      "url": "https://example.com/article",
      "source": {
        "id": "uuid",
        "name": "The Pragmatic Engineer"
      },
      "published_at": "2024-01-15T10:30:00Z",
      "relevance_score": 0.87,
      "saved_at": "2024-01-15T10:31:00Z",
      "keywords": ["rust", "memory safety", "c++"]
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": false
}
```

---

## Profile

### GET /me
Returns the authenticated user's profile plus aggregate counts (E7-S9).

**Response `200`**
```json
{
  "email": "user@example.com",
  "is_admin": false,
  "saved_count": 42,
  "keyword_count": 18,
  "source_count": 7
}
```

> `is_admin` is reserved for the E8 admin role; always `false` until then.

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
      "fetch_full_content": false
    }
  ]
}
```

> `fetch_full_content` mirrors the Miniflux `crawler` flag (E7-S26). When
> `true`, Miniflux fetches the full article HTML instead of relying on the
> RSS payload. The flag lives on the shared Miniflux feed, so changes are
> visible to every user subscribed to the same URL.

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
  touching the weight value — the next `cron_refresh_weights` run will
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

> Manual overrides are preserved by `cron_refresh_weights` —
> the cron skips recomputing weights when `manually_overridden = true`.

---

### DELETE /keywords
Delete **all** keyword weights for the authenticated user. Hard delete, irreversible.

**Response `204`** — no content

---

## System

### GET /stats
System and AI-enrichment health, used by the Profile screen's System section (E7-S15). All counts scoped to the authenticated user's sources / data.

**Response `200`**
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
    "total_tfidf": 384,
    "total_tfidf_fallback": 42,
    "last_error": "JSONDecodeError: Expecting value: line 1 column 1",
    "last_error_at": "2026-05-20T13:45:00Z"
  }
}
```

> `total_tfidf` counts every article enriched with TF-IDF (pure TF-IDF when AI
> is off, plus fallbacks). `total_tfidf_fallback` is the subset where AI was
> attempted and failed — useful for monitoring AI reliability.
> `last_error` / `last_error_at` are null when no fallback has ever happened.

---

### POST /admin/refresh
Trigger `cron_fetch` followed by `cron_enrich` as a background task (E7-S16).
Concurrent runs are debounced server-side; the response is identical whether a
new run started or one was already in flight.

> Will be gated by `require_admin` once E8-S1 lands. Open to every authenticated
> user for now (acceptable in the single-user self-host context).

**Response `202`**
```json
{ "status": "started" }
```
or
```json
{ "status": "already_running" }
```
