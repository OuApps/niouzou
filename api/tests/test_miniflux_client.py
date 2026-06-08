from datetime import datetime, timezone

import httpx
import pytest
import respx

from niouzou.services.miniflux_client import MinifluxClient

BASE = "http://miniflux.test"


def _entry(entry_id: int, feed_id: int = 1) -> dict:
    return {
        "id": entry_id,
        "feed_id": feed_id,
        "title": f"Title {entry_id}",
        "url": f"https://example.com/{entry_id}",
        "content": "<p>body</p>",
        "published_at": "2024-01-15T10:00:00Z",
    }


@respx.mock
async def test_list_unread_entries_parses_and_paginates():
    # First page has 2 entries, second page is empty → loop stops.
    route = respx.get(f"{BASE}/v1/entries").mock(
        side_effect=[
            httpx.Response(200, json={"total": 2, "entries": [_entry(10), _entry(11)]}),
            httpx.Response(200, json={"total": 2, "entries": []}),
        ]
    )

    async with MinifluxClient(BASE, "k") as client:
        entries = await client.list_unread_entries(max_entries=100)

    assert [e.id for e in entries] == [10, 11]
    assert entries[0].feed_id == 1
    assert entries[0].published_at == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    # Auth header is sent.
    assert route.calls[0].request.headers["X-Auth-Token"] == "k"


@respx.mock
async def test_list_unread_entries_respects_max():
    respx.get(f"{BASE}/v1/entries").mock(
        return_value=httpx.Response(
            200, json={"entries": [_entry(i) for i in range(100)]}
        )
    )
    async with MinifluxClient(BASE, "k") as client:
        entries = await client.list_unread_entries(max_entries=5)
    # We never request more than the cap, and a full page caps total at max.
    assert len(entries) == 5


@respx.mock
async def test_mark_entries_read_sends_payload():
    route = respx.put(f"{BASE}/v1/entries").mock(return_value=httpx.Response(204))
    async with MinifluxClient(BASE, "k") as client:
        await client.mark_entries_read([1, 2, 3])
    assert route.called
    import json

    assert json.loads(route.calls[0].request.content) == {
        "entry_ids": [1, 2, 3],
        "status": "read",
    }


@respx.mock
async def test_mark_entries_read_noop_when_empty():
    route = respx.put(f"{BASE}/v1/entries")
    async with MinifluxClient(BASE, "k") as client:
        await client.mark_entries_read([])
    assert not route.called


@respx.mock
async def test_create_feed_passes_crawler_flag():
    route = respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(201, json={"feed_id": 9})
    )
    async with MinifluxClient(BASE, "k") as client:
        feed_id = await client.create_feed(
            "https://x.dev/feed", category_id=1, crawler=True
        )
    assert feed_id == 9
    import json

    assert json.loads(route.calls[0].request.content) == {
        "feed_url": "https://x.dev/feed",
        "category_id": 1,
        "crawler": True,
    }


@respx.mock
async def test_create_feed_omits_crawler_when_false():
    route = respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(201, json={"feed_id": 9})
    )
    async with MinifluxClient(BASE, "k") as client:
        await client.create_feed("https://x.dev/feed", category_id=1)
    import json

    body = json.loads(route.calls[0].request.content)
    # Default-false stays out of the payload so we never overwrite an upstream
    # default Miniflux might apply.
    assert "crawler" not in body


@respx.mock
async def test_update_feed_sends_crawler():
    route = respx.put(f"{BASE}/v1/feeds/42").mock(
        return_value=httpx.Response(
            200,
            json={"id": 42, "title": "X", "feed_url": "u", "crawler": True},
        )
    )
    async with MinifluxClient(BASE, "k") as client:
        feed = await client.update_feed(42, crawler=True)
    assert feed.crawler is True
    import json

    assert json.loads(route.calls[0].request.content) == {"crawler": True}


@respx.mock
async def test_update_feed_sends_disabled():
    # E14-S2 — the disabled kwarg goes through without dragging crawler along.
    route = respx.put(f"{BASE}/v1/feeds/42").mock(
        return_value=httpx.Response(
            200,
            json={"id": 42, "title": "X", "feed_url": "u", "crawler": False},
        )
    )
    async with MinifluxClient(BASE, "k") as client:
        await client.update_feed(42, disabled=True)
    import json

    assert json.loads(route.calls[0].request.content) == {"disabled": True}


async def test_update_feed_requires_at_least_one_flag():
    # E14-S2 — accidental no-op calls would silently no-op the API; surface
    # them as programmer errors instead.
    import pytest

    async with MinifluxClient(BASE, "k") as client:
        with pytest.raises(ValueError):
            await client.update_feed(42)


@respx.mock
async def test_delete_feed_calls_endpoint():
    # E14-S2 — DELETE /v1/feeds/:id returns 204 on success.
    route = respx.delete(f"{BASE}/v1/feeds/42").mock(
        return_value=httpx.Response(204)
    )
    async with MinifluxClient(BASE, "k") as client:
        await client.delete_feed(42)
    assert route.called


@respx.mock
async def test_delete_feed_treats_404_as_noop():
    # E14-S2 — feed already gone is a fine end state, not an error.
    respx.delete(f"{BASE}/v1/feeds/42").mock(return_value=httpx.Response(404))
    async with MinifluxClient(BASE, "k") as client:
        await client.delete_feed(42)  # should not raise


@respx.mock
async def test_list_feeds_returns_crawler_state():
    respx.get(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "title": "A", "feed_url": "a", "crawler": True},
                {"id": 2, "title": "B", "feed_url": "b", "crawler": False},
                {"id": 3, "title": "C", "feed_url": "c"},  # no crawler key
            ],
        )
    )
    async with MinifluxClient(BASE, "k") as client:
        feeds = await client.list_feeds()
    assert {f.id: f.crawler for f in feeds} == {1: True, 2: False, 3: False}
