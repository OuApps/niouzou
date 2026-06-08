"""Sources tests: Miniflux feed creation, dedup, pause / hard-delete (E13-S5).

Miniflux HTTP is mocked with respx; the DB is the real local Postgres.
"""

import httpx
import pytest
import respx
from sqlalchemy import func, select

from niouzou.errors import APIError
from niouzou.models import Article, Source
from niouzou.services.sources_service import SourcesService
from tests.factories import make_article, make_source, make_user

BASE = "http://miniflux.test"
FEED_URL = "https://newsletter.example.com/feed"


def _mock_miniflux_create(
    feed_id: int = 42, title: str = "The Feed", crawler: bool = False
):
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "All"}])
    )
    respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(201, json={"feed_id": feed_id})
    )
    respx.get(f"{BASE}/v1/feeds/{feed_id}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": feed_id,
                "title": title,
                "feed_url": FEED_URL,
                "crawler": crawler,
            },
        )
    )


@respx.mock
async def test_create_source_registers_feed(db_session):
    user = await make_user(db_session)
    await db_session.commit()
    _mock_miniflux_create()

    out = await SourcesService(db_session).create_source(user.id, FEED_URL)
    await db_session.commit()

    assert out.name == "The Feed"
    assert out.url == FEED_URL
    source = await db_session.scalar(select(Source).where(Source.id == out.id))
    assert source.miniflux_feed_id == 42


@respx.mock
async def test_duplicate_url_conflicts(db_session):
    user = await make_user(db_session)
    await db_session.commit()
    _mock_miniflux_create()

    svc = SourcesService(db_session)
    await svc.create_source(user.id, FEED_URL)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await svc.create_source(user.id, FEED_URL)
    assert exc.value.status_code == 409


@respx.mock
async def test_deactivate_keeps_articles_and_marks_source_inactive(db_session):
    # Empty feed list — list_sources still calls Miniflux for crawler state.
    respx.get(f"{BASE}/v1/feeds").mock(return_value=httpx.Response(200, json=[]))
    # E14-S2 — sole subscriber pause triggers PUT /v1/feeds/7 disabled:true.
    put_disabled = respx.put(f"{BASE}/v1/feeds/7").mock(
        return_value=httpx.Response(
            200,
            json={"id": 7, "title": "x", "feed_url": "u", "crawler": False},
        )
    )
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=7)
    await make_article(db_session, source, title="kept")
    await db_session.commit()

    svc = SourcesService(db_session)
    await svc.deactivate_source(user.id, source.id)
    await db_session.commit()

    # Article survives a pause.
    assert await db_session.scalar(select(func.count()).select_from(Article)) == 1
    # Source is still listed, marked inactive.
    listed = await svc.list_sources(user.id)
    assert len(listed.sources) == 1
    assert listed.sources[0].active is False
    # Miniflux feed disabled because no other subscriber remained active.
    assert put_disabled.called
    import json

    assert json.loads(put_disabled.calls[0].request.content) == {"disabled": True}


@respx.mock
async def test_hard_delete_cascades_to_articles(db_session):
    # E14-S2 — sole subscriber hard delete also unsubscribes Miniflux.
    delete_route = respx.delete(f"{BASE}/v1/feeds/8").mock(
        return_value=httpx.Response(204)
    )
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=8)
    await make_article(db_session, source, title="will-be-gone")
    await db_session.commit()

    await SourcesService(db_session).hard_delete_source(user.id, source.id)
    await db_session.commit()

    assert await db_session.scalar(select(func.count()).select_from(Source)) == 0
    # FK ON DELETE CASCADE wipes the article too.
    assert await db_session.scalar(select(func.count()).select_from(Article)) == 0
    assert delete_route.called


@respx.mock
async def test_reactivating_paused_source_via_update(db_session):
    respx.get(f"{BASE}/v1/feeds").mock(return_value=httpx.Response(200, json=[]))
    # E14-S2 — accept both the pause (disabled:true) and the resume
    # (disabled:false) on the same feed via a single mock that records
    # every call.
    put_route = respx.put(f"{BASE}/v1/feeds/9").mock(
        return_value=httpx.Response(
            200,
            json={"id": 9, "title": "x", "feed_url": "u", "crawler": False},
        )
    )
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=9)
    await db_session.commit()

    svc = SourcesService(db_session)
    await svc.deactivate_source(user.id, source.id)
    await db_session.commit()

    out = await svc.update_source(user.id, source.id, active=True)
    await db_session.commit()

    assert out.active is True
    import json

    # Both transitions reached Miniflux, with the right payloads.
    payloads = [json.loads(c.request.content) for c in put_route.calls]
    assert payloads == [{"disabled": True}, {"disabled": False}]


async def test_update_source_rejects_empty_body(db_session):
    """E13-S5 — PATCH with no fields is a no-op request; reject as 400."""
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=10)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await SourcesService(db_session).update_source(user.id, source.id)
    assert exc.value.status_code == 400


async def test_update_source_full_content_on_paused_source_404s(db_session):
    """E13-S5 — fetch_full_content updates must not hit Miniflux on a paused row."""
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=11)
    await db_session.commit()

    svc = SourcesService(db_session)
    await svc.deactivate_source(user.id, source.id)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await svc.update_source(user.id, source.id, fetch_full_content=True)
    assert exc.value.status_code == 404


@respx.mock
async def test_readding_removed_source_revives_it(db_session):
    user = await make_user(db_session)
    await db_session.commit()
    _mock_miniflux_create()

    svc = SourcesService(db_session)
    created = await svc.create_source(user.id, FEED_URL)
    await db_session.commit()
    await svc.deactivate_source(user.id, created.id)
    await db_session.commit()

    # Re-adding should revive the same row without hitting Miniflux again.
    respx.reset()
    revived = await svc.create_source(user.id, FEED_URL)
    await db_session.commit()

    assert revived.id == created.id
    listed = await svc.list_sources(user.id)
    assert len(listed.sources) == 1


@respx.mock
async def test_second_user_reuses_existing_miniflux_feed(db_session):
    # Miniflux rejects a second POST /v1/feeds for the same URL with 4xx; the
    # sources service must recover by looking up the existing feed id so user B
    # can still subscribe (E7-S14).
    user_a = await make_user(db_session, email="a@test.dev")
    user_b = await make_user(db_session, email="b@test.dev")
    await db_session.commit()
    _mock_miniflux_create(feed_id=42)

    await SourcesService(db_session).create_source(user_a.id, FEED_URL)
    await db_session.commit()

    # User B: POST fails (feed already exists), but GET /v1/feeds returns it.
    respx.reset()
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "All"}])
    )
    respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(
            400, json={"error_message": "This feed already exists."}
        )
    )
    respx.get(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": 42, "title": "The Feed", "feed_url": FEED_URL}],
        )
    )
    respx.get(f"{BASE}/v1/feeds/42").mock(
        return_value=httpx.Response(
            200, json={"id": 42, "title": "The Feed", "feed_url": FEED_URL}
        )
    )

    out_b = await SourcesService(db_session).create_source(user_b.id, FEED_URL)
    await db_session.commit()

    # Both users now point at the same Miniflux feed id.
    rows = await db_session.scalars(
        select(Source).where(Source.miniflux_feed_id == 42)
    )
    sources = rows.all()
    assert len(sources) == 2
    assert {s.user_id for s in sources} == {user_a.id, user_b.id}
    assert out_b.name == "The Feed"


@respx.mock
async def test_create_source_passes_crawler_to_miniflux(db_session):
    user = await make_user(db_session)
    await db_session.commit()
    cat = respx.get(f"{BASE}/v1/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "All"}])
    )
    post = respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(201, json={"feed_id": 42})
    )
    respx.get(f"{BASE}/v1/feeds/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "title": "The Feed",
                "feed_url": FEED_URL,
                "crawler": True,
            },
        )
    )

    out = await SourcesService(db_session).create_source(
        user.id, FEED_URL, fetch_full_content=True
    )
    await db_session.commit()

    assert out.fetch_full_content is True
    import json

    body = json.loads(post.calls[0].request.content)
    assert body.get("crawler") is True
    assert cat.called


@respx.mock
async def test_create_source_second_user_with_crawler_updates_shared_feed(db_session):
    user_a = await make_user(db_session, email="a@test.dev")
    user_b = await make_user(db_session, email="b@test.dev")
    await db_session.commit()
    _mock_miniflux_create(feed_id=42)

    await SourcesService(db_session).create_source(user_a.id, FEED_URL)
    await db_session.commit()

    respx.reset()
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "All"}])
    )
    respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(
            400, json={"error_message": "This feed already exists."}
        )
    )
    respx.get(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 42, "title": "The Feed", "feed_url": FEED_URL, "crawler": False}
            ],
        )
    )
    put = respx.put(f"{BASE}/v1/feeds/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "title": "The Feed",
                "feed_url": FEED_URL,
                "crawler": True,
            },
        )
    )
    respx.get(f"{BASE}/v1/feeds/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "title": "The Feed",
                "feed_url": FEED_URL,
                "crawler": True,
            },
        )
    )

    out_b = await SourcesService(db_session).create_source(
        user_b.id, FEED_URL, fetch_full_content=True
    )
    await db_session.commit()

    assert out_b.fetch_full_content is True
    assert put.called


@respx.mock
async def test_update_source_toggles_crawler(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=77)
    await db_session.commit()

    put = respx.put(f"{BASE}/v1/feeds/77").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 77,
                "title": source.name,
                "feed_url": source.url,
                "crawler": True,
            },
        )
    )

    out = await SourcesService(db_session).update_source(
        user.id, source.id, fetch_full_content=True
    )

    assert out.fetch_full_content is True
    assert put.called
    import json

    assert json.loads(put.calls[0].request.content) == {"crawler": True}


@respx.mock
async def test_update_source_404_for_foreign_source(db_session):
    owner = await make_user(db_session, email="o@test.dev")
    intruder = await make_user(db_session, email="i@test.dev")
    source = await make_source(db_session, owner, feed_id=77)
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await SourcesService(db_session).update_source(
            intruder.id, source.id, fetch_full_content=True
        )
    assert exc.value.status_code == 404


@respx.mock
async def test_list_sources_surfaces_crawler_state(db_session):
    user = await make_user(db_session)
    s1 = await make_source(db_session, user, feed_id=1, name="A")
    s2 = await make_source(db_session, user, feed_id=2, name="B")
    await db_session.commit()
    respx.get(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 1, "title": "A", "feed_url": s1.url, "crawler": True},
                {"id": 2, "title": "B", "feed_url": s2.url, "crawler": False},
            ],
        )
    )

    listed = await SourcesService(db_session).list_sources(user.id)

    by_id = {s.id: s for s in listed.sources}
    assert by_id[s1.id].fetch_full_content is True
    assert by_id[s2.id].fetch_full_content is False


@respx.mock
async def test_list_sources_falls_back_when_miniflux_down(db_session):
    user = await make_user(db_session)
    await make_source(db_session, user, feed_id=1, name="A")
    await db_session.commit()
    respx.get(f"{BASE}/v1/feeds").mock(return_value=httpx.Response(500))

    listed = await SourcesService(db_session).list_sources(user.id)

    # Service degrades gracefully: still returns the rows, crawler defaults false.
    assert len(listed.sources) == 1
    assert listed.sources[0].fetch_full_content is False


@respx.mock
async def test_deactivate_does_not_disable_feed_when_other_user_still_active(db_session):
    # E14-S2 — when another active source still references the feed, pausing
    # one source must leave the Miniflux feed enabled (the other user still
    # wants its entries).
    respx.get(f"{BASE}/v1/feeds").mock(return_value=httpx.Response(200, json=[]))
    # If a PUT slips through, this raises a respx unmatched-route error and
    # fails the test (no fallback mock for PUT on this feed).
    user_a = await make_user(db_session, email="a@test.dev")
    user_b = await make_user(db_session, email="b@test.dev")
    source_a = await make_source(db_session, user_a, feed_id=12)
    await make_source(db_session, user_b, feed_id=12)
    await db_session.commit()

    await SourcesService(db_session).deactivate_source(user_a.id, source_a.id)
    await db_session.commit()
    # Reaching here without an unmatched-route error proves no PUT was sent.


@respx.mock
async def test_resuming_keeps_feed_disabled_call_off_when_other_user_active(db_session):
    # E14-S2 — when another active subscriber kept the feed enabled in
    # Miniflux all along, resuming a paused source must NOT re-PUT.
    respx.get(f"{BASE}/v1/feeds").mock(return_value=httpx.Response(200, json=[]))
    user_a = await make_user(db_session, email="a@test.dev")
    user_b = await make_user(db_session, email="b@test.dev")
    source_a = await make_source(db_session, user_a, feed_id=13)
    await make_source(db_session, user_b, feed_id=13)
    # Pause user A first — guarded by a real mock so we know the only call
    # accounted for is the pause one. Then user B will be the only active.
    pause_put = respx.put(f"{BASE}/v1/feeds/13").mock(
        return_value=httpx.Response(
            200,
            json={"id": 13, "title": "x", "feed_url": "u", "crawler": False},
        )
    )
    await db_session.commit()

    svc = SourcesService(db_session)
    await svc.deactivate_source(user_a.id, source_a.id)
    await db_session.commit()
    # Pause didn't disable the feed (user B still active).
    assert not pause_put.called

    # Resume — feed was never disabled, so no PUT either.
    await svc.update_source(user_a.id, source_a.id, active=True)
    await db_session.commit()
    assert not pause_put.called


@respx.mock
async def test_hard_delete_shared_feed_does_not_unsubscribe_miniflux(db_session):
    # E14-S2 — when another (active or paused) source references the feed,
    # hard-deleting one must not remove the shared feed from Miniflux.
    user_a = await make_user(db_session, email="a@test.dev")
    user_b = await make_user(db_session, email="b@test.dev")
    source_a = await make_source(db_session, user_a, feed_id=14)
    await make_source(db_session, user_b, feed_id=14)
    await db_session.commit()

    # No DELETE mock → respx would raise on an unmatched call.
    await SourcesService(db_session).hard_delete_source(user_a.id, source_a.id)
    await db_session.commit()

    remaining = await db_session.scalar(
        select(func.count()).select_from(Source).where(Source.miniflux_feed_id == 14)
    )
    assert remaining == 1


@respx.mock
async def test_pause_swallows_miniflux_failure(db_session):
    # E14-S2 — Niouzou state of truth wins. A Miniflux PUT failure logs but
    # doesn't roll back the soft delete; cron_fetch (E14-S1) handles the
    # backlog defensively.
    respx.get(f"{BASE}/v1/feeds").mock(return_value=httpx.Response(200, json=[]))
    respx.put(f"{BASE}/v1/feeds/15").mock(return_value=httpx.Response(500))
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=15)
    await db_session.commit()

    await SourcesService(db_session).deactivate_source(user.id, source.id)
    await db_session.commit()

    # Soft delete went through despite the 500.
    refreshed = await db_session.scalar(select(Source).where(Source.id == source.id))
    assert refreshed.deleted_at is not None


@respx.mock
async def test_hard_delete_swallows_miniflux_404(db_session):
    # E14-S2 — Miniflux returning 404 on DELETE is treated as a no-op (the
    # feed already gone is fine). The Niouzou hard delete still cascades.
    respx.delete(f"{BASE}/v1/feeds/16").mock(return_value=httpx.Response(404))
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=16)
    await make_article(db_session, source, title="x")
    await db_session.commit()

    await SourcesService(db_session).hard_delete_source(user.id, source.id)
    await db_session.commit()

    assert await db_session.scalar(select(func.count()).select_from(Source)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Article)) == 0


@respx.mock
async def test_bad_feed_url_returns_400(db_session):
    user = await make_user(db_session)
    await db_session.commit()
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "All"}])
    )
    respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(400, json={"error_message": "bad feed"})
    )
    # Recovery path: no existing feed matches, so the original 4xx surfaces.
    respx.get(f"{BASE}/v1/feeds").mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(APIError) as exc:
        await SourcesService(db_session).create_source(user.id, FEED_URL)
    assert exc.value.status_code == 400
