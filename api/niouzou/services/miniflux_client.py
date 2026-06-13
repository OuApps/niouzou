"""Thin async client over the Miniflux REST API.

Miniflux is treated as a read-only data source: Niouzou pulls entries and
marks them read, but never modifies feed configuration here (feed creation
belongs to the sources service in Epic 3).

API reference: https://miniflux.app/docs/api.html
Auth: the ``X-Auth-Token`` header carries the Miniflux API key.
"""

from dataclasses import dataclass
from datetime import datetime

import httpx

# Miniflux caps entries responses at 100; we page if a run needs more.
_PAGE_LIMIT = 100


@dataclass(slots=True)
class MinifluxFeed:
    """A Miniflux feed, reduced to what the sources service needs."""

    id: int
    title: str
    feed_url: str
    crawler: bool

    @classmethod
    def from_api(cls, data: dict) -> "MinifluxFeed":
        return cls(
            id=data["id"],
            title=data.get("title") or data.get("feed_url") or "(untitled feed)",
            feed_url=data.get("feed_url") or "",
            crawler=bool(data.get("crawler", False)),
        )


@dataclass(slots=True)
class MinifluxEntry:
    """A single Miniflux entry, reduced to the fields cron_fetch needs."""

    id: int
    feed_id: int
    title: str
    url: str
    content: str | None
    published_at: datetime | None
    og_image_url: str | None

    @classmethod
    def from_api(cls, data: dict) -> "MinifluxEntry":
        return cls(
            id=data["id"],
            feed_id=data["feed_id"],
            title=data.get("title") or "(untitled)",
            url=data.get("url") or "",
            content=data.get("content") or None,
            published_at=_parse_dt(data.get("published_at")),
            og_image_url=_first_image_enclosure(data.get("enclosures")),
        )


def _first_image_enclosure(enclosures: object) -> str | None:
    """Return the first image URL among Miniflux entry enclosures.

    Miniflux exposes media via ``enclosures`` ([{url, mime_type, ...}]). Many
    feeds advertise their cover image here, so it's the cheapest source of
    ``og_image_url`` — no extra fetch required.
    """
    if not isinstance(enclosures, list):
        return None
    for enc in enclosures:
        if not isinstance(enc, dict):
            continue
        mime = (enc.get("mime_type") or "").lower()
        url = enc.get("url")
        if mime.startswith("image/") and url:
            return url
    return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Miniflux returns RFC 3339 timestamps, e.g. "2024-01-15T10:00:00Z".
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MinifluxClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Auth-Token": api_key},
            timeout=timeout,
        )

    async def __aenter__(self) -> "MinifluxClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_unread_entries(self, *, max_entries: int) -> list[MinifluxEntry]:
        """Fetch up to ``max_entries`` unread entries, oldest first.

        Oldest-first ordering means an interrupted run still makes forward
        progress: the entries it managed to mark read won't be re-fetched.
        """
        entries: list[MinifluxEntry] = []
        offset = 0
        while len(entries) < max_entries:
            limit = min(_PAGE_LIMIT, max_entries - len(entries))
            resp = await self._client.get(
                "/v1/entries",
                params={
                    "status": "unread",
                    "limit": limit,
                    "offset": offset,
                    "order": "published_at",
                    "direction": "asc",
                },
            )
            resp.raise_for_status()
            page = resp.json().get("entries", [])
            if not page:
                break
            entries.extend(MinifluxEntry.from_api(e) for e in page)
            offset += len(page)
        # Defensive cap: never return more than asked, even if a page overshoots.
        return entries[:max_entries]

    async def get_entry_content(self, entry_id: int) -> str | None:
        """Return an entry's raw RSS ``content`` (HTML), or ``None`` if gone.

        Used by the E10-S6 boilerplate backfill to recover the original RSS
        teaser after ``article.content`` was overwritten with a paywall footer.
        A purged/missing entry (404) yields ``None`` so the caller can skip it.
        """
        resp = await self._client.get(f"/v1/entries/{entry_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("content") or None

    async def default_category_id(self) -> int:
        """Return a category id to file new feeds under.

        Miniflux requires a category when creating a feed; every instance has a
        built-in "All" category, so the first one is a safe default.
        """
        resp = await self._client.get("/v1/categories")
        resp.raise_for_status()
        categories = resp.json()
        if not categories:
            raise RuntimeError("Miniflux returned no categories")
        return categories[0]["id"]

    async def create_feed(
        self, feed_url: str, *, category_id: int, crawler: bool = False
    ) -> int:
        """Subscribe Miniflux to ``feed_url``. Returns the new feed id.

        ``crawler=True`` tells Miniflux to fetch the full article HTML for each
        entry rather than relying on whatever the RSS feed inlines — useful
        when the feed only exposes teasers.
        """
        payload: dict = {"feed_url": feed_url, "category_id": category_id}
        if crawler:
            payload["crawler"] = True
        resp = await self._client.post("/v1/feeds", json=payload)
        resp.raise_for_status()
        return resp.json()["feed_id"]

    async def update_feed(
        self,
        feed_id: int,
        *,
        crawler: bool | None = None,
        disabled: bool | None = None,
    ) -> MinifluxFeed:
        """Patch feed flags. ``crawler`` toggles full-content fetching;
        ``disabled`` pauses Miniflux's polling of the feed (E14-S2).

        Both kwargs are optional — the payload only includes fields the
        caller passed, so a partial update doesn't overwrite the other flag.
        """
        payload: dict = {}
        if crawler is not None:
            payload["crawler"] = crawler
        if disabled is not None:
            payload["disabled"] = disabled
        if not payload:
            raise ValueError("update_feed requires at least one of crawler/disabled")
        resp = await self._client.put(f"/v1/feeds/{feed_id}", json=payload)
        resp.raise_for_status()
        return MinifluxFeed.from_api(resp.json())

    async def delete_feed(self, feed_id: int) -> None:
        """Unsubscribe Miniflux from a feed and purge its entries (E14-S2).

        Used when no Niouzou source — active or paused — references the feed
        anymore. Miniflux returns 204 on success. 404 (already gone) is
        treated as a no-op so a retry after a partial failure is safe.
        """
        resp = await self._client.delete(f"/v1/feeds/{feed_id}")
        if resp.status_code == 404:
            return
        resp.raise_for_status()

    async def find_feed_by_url(self, feed_url: str) -> int | None:
        """Return the id of an existing feed whose ``feed_url`` matches, if any.

        Miniflux has no server-side filter on ``/v1/feeds``, so this lists all
        feeds and matches client-side. Only used to recover from the "feed
        already exists" 4xx when a second user subscribes to the same URL.
        """
        resp = await self._client.get("/v1/feeds")
        resp.raise_for_status()
        for feed in resp.json():
            if feed.get("feed_url") == feed_url:
                return feed["id"]
        return None

    async def list_feeds(self) -> list[MinifluxFeed]:
        """Return all feeds Miniflux currently has subscribed."""
        resp = await self._client.get("/v1/feeds")
        resp.raise_for_status()
        return [MinifluxFeed.from_api(f) for f in resp.json()]

    async def get_feed(self, feed_id: int) -> MinifluxFeed:
        """Fetch a feed's metadata (used to discover its display title)."""
        resp = await self._client.get(f"/v1/feeds/{feed_id}")
        resp.raise_for_status()
        return MinifluxFeed.from_api(resp.json())

    async def mark_entries_read(self, entry_ids: list[int]) -> None:
        """Mark the given entries as read so they aren't fetched again."""
        if not entry_ids:
            return
        resp = await self._client.put(
            "/v1/entries",
            json={"entry_ids": entry_ids, "status": "read"},
        )
        resp.raise_for_status()
