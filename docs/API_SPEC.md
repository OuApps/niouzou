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
      "relevance_score": 0.87
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": true
}
```

> `next_cursor` is null when there are no more articles.
> Cursor encodes the last article's `relevance_score` + `id` to ensure stable pagination.

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
  }
}
```

> `feedback` is null if the user has not interacted with the article yet.
> `summary_executive` is null when AI enrichment is disabled.

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
      "saved_at": "2024-01-15T10:31:00Z"
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": false
}
```

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
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

---

### POST /sources
Add a new RSS source. The backend registers the feed in Miniflux and creates the source record.

**Request**
```json
{
  "url": "https://newsletter.pragmaticengineer.com/feed"
}
```

**Response `201`**
```json
{
  "id": "uuid",
  "name": "The Pragmatic Engineer",
  "url": "https://newsletter.pragmaticengineer.com/feed",
  "created_at": "2024-01-15T10:00:00Z"
}
```

> The feed name is auto-discovered from the RSS feed metadata.
> Returns `409` if the source URL already exists for this user.

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
      "updated_at": "2024-01-15T10:00:00Z"
    },
    {
      "term": "php",
      "weight": -1.8,
      "like_count": 0,
      "dislike_count": 9,
      "updated_at": "2024-01-14T08:00:00Z"
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjoiLi4uIn0=",
  "has_more": false
}
```

---

### PATCH /keywords/{term}
Manually override the weight for a keyword.

**Request**
```json
{
  "weight": 0.0
}
```

**Response `200`**
```json
{
  "term": "rust",
  "weight": 0.0,
  "like_count": 12,
  "dislike_count": 1,
  "updated_at": "2024-01-15T11:00:00Z"
}
```

> Manual overrides are preserved by `cron_refresh_weights` —
> a `manually_overridden` flag (bool) is set on the row and
> the cron skips recomputing weights for flagged rows.
