"""MCP server + service account keys (E22).

Pure key-helper tests run without a DB. Service / endpoint tests use the
``db_session`` fixture (skip cleanly when Postgres is unreachable). Endpoint
tests drive the app over httpx ``ASGITransport`` — the same pattern as
``test_chat.py`` — so they exercise auth, routing and the JSON-RPC transport
end to end.
"""

import json

import httpx
import pytest

from niouzou.errors import APIError
from niouzou.security import (
    API_KEY_PREFIX,
    api_key_prefix,
    generate_api_key,
    hash_api_key,
)
from niouzou.services.service_account_service import ServiceAccountService
from tests.factories import make_article, make_source, make_user, set_relevance

# ── Pure key helpers (no DB) ────────────────────────────────────────────────


def test_generate_api_key_shape():
    key = generate_api_key()
    assert key.startswith(API_KEY_PREFIX)
    assert len(key) > len(API_KEY_PREFIX) + 20
    # Two calls never collide.
    assert generate_api_key() != generate_api_key()


def test_hash_api_key_is_deterministic_and_hex():
    key = generate_api_key()
    h = hash_api_key(key)
    assert h == hash_api_key(key)
    assert len(h) == 64  # sha256 hex
    assert hash_api_key(generate_api_key()) != h


def test_api_key_prefix():
    key = "nzk_ABCDEFGHIJKLMNOP"
    assert api_key_prefix(key) == "nzk_ABCDEFGH"


# ── ServiceAccountService (DB) ──────────────────────────────────────────────


async def test_create_returns_token_and_stores_only_hash(db_session):
    user = await make_user(db_session)
    await db_session.commit()

    key, token = await ServiceAccountService(db_session).create(user.id, "CLI")
    await db_session.commit()

    assert token.startswith(API_KEY_PREFIX)
    assert key.name == "CLI"
    assert key.prefix == api_key_prefix(token)
    # The raw token is never persisted — only its hash.
    assert key.key_hash == hash_api_key(token)
    assert token not in key.key_hash


async def test_authenticate_resolves_owner_and_stamps_last_used(db_session):
    user = await make_user(db_session)
    svc = ServiceAccountService(db_session)
    key, token = await svc.create(user.id, "CLI")
    await db_session.commit()
    assert key.last_used_at is None

    resolved = await svc.authenticate(token)
    assert resolved is not None
    assert resolved.id == user.id
    await db_session.refresh(key)
    assert key.last_used_at is not None


async def test_authenticate_rejects_unknown_and_empty(db_session):
    svc = ServiceAccountService(db_session)
    assert await svc.authenticate("nzk_nope") is None
    assert await svc.authenticate("") is None


async def test_authenticate_rejects_revoked(db_session):
    user = await make_user(db_session)
    svc = ServiceAccountService(db_session)
    key, token = await svc.create(user.id, "CLI")
    await db_session.commit()

    await svc.revoke(key.id)
    await db_session.commit()
    assert await svc.authenticate(token) is None


async def test_revoke_unknown_raises_404(db_session):
    import uuid

    with pytest.raises(APIError) as exc:
        await ServiceAccountService(db_session).revoke(uuid.uuid4())
    assert exc.value.status_code == 404


async def test_list_all_newest_first(db_session):
    user = await make_user(db_session)
    svc = ServiceAccountService(db_session)
    k1, _ = await svc.create(user.id, "first")
    k2, _ = await svc.create(user.id, "second")
    await db_session.commit()

    keys = await svc.list_all()
    assert [k.name for k in keys][:2] == ["second", "first"]


# ── Admin endpoints (over ASGITransport) ────────────────────────────────────


async def _admin_client(admin_user):
    from niouzou.deps import get_current_user
    from niouzou.main import app

    app.dependency_overrides[get_current_user] = lambda: admin_user
    transport = httpx.ASGITransport(app=app)
    return app, httpx.AsyncClient(transport=transport, base_url="http://t")


async def test_admin_create_list_revoke_flow(db_session):
    admin = await make_user(db_session, email="admin@test.dev")
    admin.is_admin = True
    await db_session.commit()

    app, client = await _admin_client(admin)
    try:
        async with client:
            # Create — token present exactly once.
            resp = await client.post("/api/v1/admin/mcp-keys", json={"name": "CLI"})
            assert resp.status_code == 201
            created = resp.json()
            assert created["token"].startswith(API_KEY_PREFIX)
            assert created["name"] == "CLI"
            key_id = created["id"]

            # List — no token leaked.
            resp = await client.get("/api/v1/admin/mcp-keys")
            assert resp.status_code == 200
            rows = resp.json()
            assert len(rows) == 1
            assert "token" not in rows[0]
            assert rows[0]["revoked_at"] is None

            # Revoke.
            resp = await client.delete(f"/api/v1/admin/mcp-keys/{key_id}")
            assert resp.status_code == 204

            resp = await client.get("/api/v1/admin/mcp-keys")
            assert resp.json()[0]["revoked_at"] is not None
    finally:
        app.dependency_overrides.clear()


async def test_admin_endpoints_forbid_non_admin(db_session):
    user = await make_user(db_session, email="plain@test.dev")
    await db_session.commit()

    app, client = await _admin_client(user)
    try:
        async with client:
            resp = await client.get("/api/v1/admin/mcp-keys")
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ── MCP endpoint (JSON-RPC over ASGITransport) ──────────────────────────────


def _mcp_client():
    from niouzou.main import app

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://t")


async def _make_key(db_session, *, email="mcp@test.dev"):
    user = await make_user(db_session, email=email)
    _, token = await ServiceAccountService(db_session).create(user.id, "MCP")
    await db_session.commit()
    return user, token


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def test_mcp_requires_valid_key(db_session):
    async with _mcp_client() as client:
        # No auth header.
        resp = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
        )
        assert resp.status_code == 401
        # Bogus key.
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=_auth("nzk_bogus"),
        )
        assert resp.status_code == 401


async def test_mcp_initialize_and_tools_list(db_session):
    _, token = await _make_key(db_session)
    async with _mcp_client() as client:
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["serverInfo"]["name"] == "niouzou"
        assert body["result"]["protocolVersion"] == "2025-06-18"

        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=_auth(token),
        )
        names = {t["name"] for t in resp.json()["result"]["tools"]}
        assert names == {"list_feed", "search_articles", "get_article"}


async def test_mcp_notification_returns_202(db_session):
    _, token = await _make_key(db_session)
    async with _mcp_client() as client:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=_auth(token),
        )
        assert resp.status_code == 202
        assert resp.content == b""


async def test_mcp_list_feed_returns_scored_articles(db_session):
    user, token = await _make_key(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, title="Rust wins")
    await set_relevance(db_session, article, user, 0.9)
    await db_session.commit()

    async with _mcp_client() as client:
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "list_feed", "arguments": {"limit": 10}},
            },
            headers=_auth(token),
        )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload["count"] == 1
        assert payload["articles"][0]["title"] == "Rust wins"
        assert payload["articles"][0]["score"] == 0.9


async def test_mcp_get_article_returns_content(db_session):
    user, token = await _make_key(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, title="Deep dive")
    article.content = "Full article body here."
    await set_relevance(db_session, article, user, 0.5)
    await db_session.commit()

    async with _mcp_client() as client:
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "get_article",
                    "arguments": {"article_id": str(article.id)},
                },
            },
            headers=_auth(token),
        )
        payload = json.loads(resp.json()["result"]["content"][0]["text"])
        assert payload["title"] == "Deep dive"
        assert payload["content"] == "Full article body here."


async def test_mcp_get_article_unknown_is_error_result(db_session):
    import uuid

    _, token = await _make_key(db_session)
    async with _mcp_client() as client:
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "get_article",
                    "arguments": {"article_id": str(uuid.uuid4())},
                },
            },
            headers=_auth(token),
        )
        # Tool-level failure → result with isError, not a JSON-RPC error.
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["isError"] is True
        assert "not found" in result["content"][0]["text"].lower()


async def test_mcp_unknown_method_returns_jsonrpc_error(db_session):
    _, token = await _make_key(db_session)
    async with _mcp_client() as client:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 8, "method": "does/not/exist"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == -32601


async def test_mcp_batch_request(db_session):
    _, token = await _make_key(db_session)
    async with _mcp_client() as client:
        resp = await client.post(
            "/mcp",
            json=[
                {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            ],
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Two responses (ping + tools/list); the notification yields nothing.
        assert isinstance(body, list)
        assert {r["id"] for r in body} == {1, 2}


async def test_mcp_key_scopes_to_owner(db_session):
    """A key only sees its owner's articles, never another user's."""
    owner, token = await _make_key(db_session, email="owner@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    other_source = await make_source(db_session, other, feed_id=99)
    other_article = await make_article(db_session, other_source, title="Secret")
    await set_relevance(db_session, other_article, other, 0.9)
    await db_session.commit()

    async with _mcp_client() as client:
        # list_feed is empty for the owner (no articles of their own).
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_feed", "arguments": {}},
            },
            headers=_auth(token),
        )
        payload = json.loads(resp.json()["result"]["content"][0]["text"])
        assert payload["count"] == 0

        # get_article on the other user's article is not found for this key.
        resp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_article",
                    "arguments": {"article_id": str(other_article.id)},
                },
            },
            headers=_auth(token),
        )
        assert resp.json()["result"]["isError"] is True
