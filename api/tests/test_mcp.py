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
from niouzou.services.mcp_service import niouzou_article_url
from niouzou.services.service_account_service import ServiceAccountService
from tests.factories import make_article, make_source, make_user

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


async def test_authenticate_resolves_key_and_stamps_last_used(db_session):
    user = await make_user(db_session)
    svc = ServiceAccountService(db_session)
    key, token = await svc.create(user.id, "CLI")
    await db_session.commit()
    assert key.last_used_at is None

    # E23-S1 — authenticate returns the key itself (the MCP has no user context).
    resolved = await svc.authenticate(token)
    assert resolved is not None
    assert resolved.id == key.id
    assert resolved.user_id == user.id
    # authenticate stamps last_used_at on the session but leaves the commit to
    # the request boundary — persist it, then reload to confirm it stuck.
    await db_session.commit()
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
    # Commit between creates so the two rows get distinct ``now()`` timestamps
    # (now() is transaction-start time — same for rows made in one txn). This
    # mirrors real usage: each key is minted in its own request/transaction.
    await svc.create(user.id, "first")
    await db_session.commit()
    await svc.create(user.id, "second")
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


# ── FastMCP server (E22-S3) ─────────────────────────────────────────────────
#
# A FastMCP session manager can only be run() once, so each test builds a fresh
# server via ``build_mcp_server`` and enters its own lifespan (keeping the
# per-test event-loop model the rest of the suite relies on). The tool logic is
# also covered directly through McpService / the service tests above.

_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _auth(token: str) -> dict:
    return {**_MCP_HEADERS, "Authorization": f"Bearer {token}"}


class _mcp_server:
    """Async context manager yielding an httpx client bound to a fresh MCP
    server whose Streamable HTTP session manager is running."""

    async def __aenter__(self):
        from niouzou.mcp_app import build_mcp_server

        _, asgi_app, lifespan = build_mcp_server()
        self._lifespan = lifespan(None)
        await self._lifespan.__aenter__()
        transport = httpx.ASGITransport(app=asgi_app)
        self._client = httpx.AsyncClient(
            transport=transport, base_url="http://mcp.test"
        )
        return self._client

    async def __aexit__(self, *exc):
        await self._client.aclose()
        await self._lifespan.__aexit__(*exc)


async def _make_key(db_session, *, email="mcp@test.dev"):
    user = await make_user(db_session, email=email)
    _, token = await ServiceAccountService(db_session).create(user.id, "MCP")
    await db_session.commit()
    return user, token


def _call_body(resp) -> dict:
    """Unpack a tools/call result.

    A success carries a JSON payload in its text block; an ``isError`` result
    carries the plain error message (not JSON), so only decode on success.
    """
    result = resp.json()["result"]
    is_error = result["isError"]
    text = result["content"][0]["text"]
    return {
        "isError": is_error,
        "text": text,
        "payload": None if is_error else json.loads(text),
    }


async def test_mcp_registers_three_tools():
    """No DB / no HTTP — the shared server advertises exactly our three tools."""
    from niouzou.mcp_app import mcp

    tools = await mcp.list_tools()
    assert {t.name for t in tools} == {
        "list_recent_articles",
        "search_articles",
        "get_article",
    }


async def test_mcp_requires_valid_key(db_session):
    async with _mcp_server() as client:
        # No auth header at all.
        resp = await client.post(
            "/mcp",
            headers=_MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert resp.status_code == 401
        # A bogus key.
        resp = await client.post(
            "/mcp",
            headers=_auth("nzk_bogus"),
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert resp.status_code == 401


async def test_mcp_initialize_and_tools_list(db_session):
    _, token = await _make_key(db_session)
    async with _mcp_server() as client:
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["serverInfo"]["name"] == "niouzou"

        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        names = {t["name"] for t in resp.json()["result"]["tools"]}
        assert names == {"list_recent_articles", "search_articles", "get_article"}


async def test_mcp_revoked_key_is_rejected(db_session):
    user = await make_user(db_session, email="rev@test.dev")
    svc = ServiceAccountService(db_session)
    key, token = await svc.create(user.id, "MCP")
    await db_session.commit()
    await svc.revoke(key.id)
    await db_session.commit()

    async with _mcp_server() as client:
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert resp.status_code == 401


async def test_mcp_list_recent_articles_has_no_score(db_session):
    # The key's creator owns nothing; the tool still lists the whole base.
    user, token = await _make_key(db_session)
    owner = await make_user(db_session, email="writer@test.dev")
    source = await make_source(db_session, owner)
    await make_article(db_session, source, title="Rust wins")
    await db_session.commit()

    async with _mcp_server() as client:
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "list_recent_articles",
                    "arguments": {"limit": 10},
                },
            },
        )
        assert resp.status_code == 200
        body = _call_body(resp)
        assert body["isError"] is False
        assert body["payload"]["count"] == 1
        item = body["payload"]["articles"][0]
        assert item["title"] == "Rust wins"
        # E23-S1 — the MCP never exposes scores or per-user data.
        assert "score" not in item
        assert "user_id" not in item
        # E23-S2 — every item carries a shareable Niouzou deep link.
        assert item["niouzou_url"].endswith(f"/article/{item['id']}")


async def test_mcp_search_articles_spans_whole_base(db_session):
    """Search hits any user's article and never leaks a score (E23-S1)."""
    _, token = await _make_key(db_session)
    owner = await make_user(db_session, email="writer2@test.dev")
    source = await make_source(db_session, owner)
    await make_article(db_session, source, title="Climate summit recap")
    await make_article(db_session, source, title="Rust release notes")
    await db_session.commit()

    async with _mcp_server() as client:
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "search_articles",
                    "arguments": {"query": "climate"},
                },
            },
        )
        body = _call_body(resp)
        assert body["payload"]["count"] == 1
        assert body["payload"]["articles"][0]["title"] == "Climate summit recap"
        assert "score" not in body["payload"]["articles"][0]


async def test_mcp_get_article_returns_content(db_session):
    _, token = await _make_key(db_session)
    owner = await make_user(db_session, email="writer3@test.dev")
    source = await make_source(db_session, owner)
    article = await make_article(db_session, source, title="Deep dive")
    article.content = "Full article body here."
    await db_session.commit()

    async with _mcp_server() as client:
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "get_article",
                    "arguments": {"article_id": str(article.id)},
                },
            },
        )
        body = _call_body(resp)
        assert body["payload"]["title"] == "Deep dive"
        assert body["payload"]["content"] == "Full article body here."
        assert body["payload"]["niouzou_url"].endswith(f"/article/{article.id}")
        assert "score" not in body["payload"]


async def test_mcp_get_article_unknown_is_error_result(db_session):
    import uuid

    _, token = await _make_key(db_session)
    async with _mcp_server() as client:
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "get_article",
                    "arguments": {"article_id": str(uuid.uuid4())},
                },
            },
        )
        # A tool-level failure comes back as isError, not a protocol error.
        assert resp.status_code == 200
        body = _call_body(resp)
        assert body["isError"] is True
        assert "not found" in body["text"].lower()


async def test_mcp_sees_articles_from_any_source(db_session):
    """The MCP has its own identity: it reaches any user's article (E23-S1)."""
    _, token = await _make_key(db_session, email="agent@test.dev")
    other = await make_user(db_session, email="other@test.dev")
    other_source = await make_source(db_session, other, feed_id=99)
    other_article = await make_article(db_session, other_source, title="Secret")
    await db_session.commit()

    async with _mcp_server() as client:
        # The article is visible even though the key's creator doesn't own it.
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_recent_articles", "arguments": {}},
            },
        )
        assert _call_body(resp)["payload"]["count"] == 1

        # And it's fetchable by id regardless of ownership.
        resp = await client.post(
            "/mcp",
            headers=_auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_article",
                    "arguments": {"article_id": str(other_article.id)},
                },
            },
        )
        body = _call_body(resp)
        assert body["isError"] is False
        assert body["payload"]["title"] == "Secret"


# ── Article deep-link URL helper (E23-S2) ───────────────────────────────────


def test_niouzou_article_url_uses_public_app_url(monkeypatch):
    from types import SimpleNamespace

    import niouzou.services.mcp_service as m

    monkeypatch.setattr(
        m, "get_settings", lambda: SimpleNamespace(public_app_url="https://pwa.test/")
    )
    assert niouzou_article_url("abc-123") == "https://pwa.test/article/abc-123"


def test_niouzou_article_url_falls_back_to_path(monkeypatch):
    from types import SimpleNamespace

    import niouzou.services.mcp_service as m

    monkeypatch.setattr(
        m, "get_settings", lambda: SimpleNamespace(public_app_url="")
    )
    assert niouzou_article_url("abc-123") == "/article/abc-123"
