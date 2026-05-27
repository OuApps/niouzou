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
