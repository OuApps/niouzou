"""Sources tests (E3-S3): Miniflux feed creation, dedup, soft delete.

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


def _mock_miniflux_create(feed_id: int = 42, title: str = "The Feed"):
    respx.get(f"{BASE}/v1/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "All"}])
    )
    respx.post(f"{BASE}/v1/feeds").mock(
        return_value=httpx.Response(201, json={"feed_id": feed_id})
    )
    respx.get(f"{BASE}/v1/feeds/{feed_id}").mock(
        return_value=httpx.Response(
            200, json={"id": feed_id, "title": title, "feed_url": FEED_URL}
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
async def test_delete_keeps_articles_and_hides_source(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user, feed_id=7)
    await make_article(db_session, source, title="kept")
    await db_session.commit()

    svc = SourcesService(db_session)
    await svc.delete_source(user.id, source.id)
    await db_session.commit()

    # Article survives the source removal.
    assert await db_session.scalar(select(func.count()).select_from(Article)) == 1
    # Source no longer listed.
    listed = await svc.list_sources(user.id)
    assert listed.sources == []


@respx.mock
async def test_readding_removed_source_revives_it(db_session):
    user = await make_user(db_session)
    await db_session.commit()
    _mock_miniflux_create()

    svc = SourcesService(db_session)
    created = await svc.create_source(user.id, FEED_URL)
    await db_session.commit()
    await svc.delete_source(user.id, created.id)
    await db_session.commit()

    # Re-adding should revive the same row without hitting Miniflux again.
    respx.reset()
    revived = await svc.create_source(user.id, FEED_URL)
    await db_session.commit()

    assert revived.id == created.id
    listed = await svc.list_sources(user.id)
    assert len(listed.sources) == 1


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

    with pytest.raises(APIError) as exc:
        await SourcesService(db_session).create_source(user.id, FEED_URL)
    assert exc.value.status_code == 400
