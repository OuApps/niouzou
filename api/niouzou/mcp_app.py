"""FastMCP server exposed at ``/mcp`` (E22).

Built on the official MCP SDK's :class:`FastMCP` (stateless Streamable HTTP,
JSON responses). It's wrapped in a tiny ASGI guard that authenticates the
service account key (``Authorization: Bearer nzk_…``) and stashes the owning
user id in a context var for the tools to read — so the whole thing drops into
the existing FastAPI app without FastMCP's OAuth machinery.

``build_mcp_server`` is a factory: a FastMCP instance's session manager can
only be ``run()`` once, so tests build a throwaway server per case rather than
re-entering the shared app's lifespan. ``main.py`` mounts the module-level
``mcp_asgi_app`` at ``/mcp`` and wires ``mcp_lifespan`` so the session manager
runs for the app's lifetime.
"""

import contextvars
import json
import uuid
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Headers
from starlette.responses import JSONResponse

from niouzou.db import session_scope
from niouzou.services.mcp_service import DEFAULT_LIMIT, McpService
from niouzou.services.service_account_service import ServiceAccountService

# Set by the auth guard for the duration of each request; read by the tools.
_current_user_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "mcp_user_id", default=None
)


def _user_id() -> uuid.UUID:
    uid = _current_user_id.get()
    if uid is None:  # pragma: no cover — the auth guard guarantees a user
        raise RuntimeError("MCP tool invoked without an authenticated user")
    return uid


def _bearer_token(headers: Headers) -> str:
    scheme, _, token = headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


class ServiceAccountAuthMiddleware:
    """ASGI guard resolving the service account key to its owning user.

    Owns ``/mcp`` and ``/mcp/`` only (any other path 404s, so the catch-all
    mount doesn't shadow the REST 404s). Rejects a missing / invalid / revoked
    key with 401 before the request reaches the MCP handler; on success it
    publishes the user id in a context var (inherited by the stateless
    request's task subtree) for the tools.
    """

    def __init__(self, app, mcp_path: str) -> None:
        self.app = app
        self._path = mcp_path
        self._paths = {mcp_path, mcp_path + "/"}

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if path not in self._paths:
            return await self._respond(
                scope, receive, send, 404, "not_found", "Not Found"
            )

        token = _bearer_token(Headers(scope=scope))
        user = None
        if token:
            async with session_scope() as session:
                user = await ServiceAccountService(session).authenticate(token)
        if user is None:
            return await self._respond(
                scope,
                receive,
                send,
                401,
                "unauthorized",
                "Invalid or revoked service account key",
            )

        # Normalise a trailing slash to the canonical path so the inner MCP
        # route always matches (no internal redirect).
        if path != self._path:
            scope = {**scope, "path": self._path, "raw_path": self._path.encode()}

        reset = _current_user_id.set(user.id)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user_id.reset(reset)

    @staticmethod
    async def _respond(scope, receive, send, status, error, message) -> None:
        response = JSONResponse({"error": error, "message": message}, status_code=status)
        await response(scope, receive, send)


def build_mcp_server():
    """Construct a fresh FastMCP server + its ASGI guard + lifespan.

    Returns ``(mcp, asgi_app, lifespan)``. Each call yields an independent
    session manager, so a test can run its own lifespan without tripping the
    "``run()`` only once per instance" guard on the shared app's server.

    DNS-rebinding protection is disabled: FastMCP defaults to allowing only
    localhost Hosts, which would 421 every request behind a real domain
    (Railway, a self-hoster's reverse proxy). That protection targets
    browser-reachable *local* servers; our endpoint is a hosted API gated by a
    service account key, so the key is the security boundary instead.
    """
    mcp = FastMCP(
        "niouzou",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )

    @mcp.tool(
        description=(
            "Return the current personalised Niouzou feed: the top-ranked "
            "articles the user hasn't seen yet, most relevant first."
        )
    )
    async def list_feed(limit: int = DEFAULT_LIMIT) -> str:
        async with session_scope() as session:
            result = await McpService(session).list_feed(_user_id(), limit)
        return json.dumps(result, ensure_ascii=False)

    @mcp.tool(
        description=(
            "Full-text search over the user's enriched articles (title and "
            "summary), newest first."
        )
    )
    async def search_articles(query: str, limit: int = DEFAULT_LIMIT) -> str:
        async with session_scope() as session:
            result = await McpService(session).search_articles(
                _user_id(), query, limit
            )
        return json.dumps(result, ensure_ascii=False)

    @mcp.tool(
        description="Fetch one article by id, including its full crawled text content."
    )
    async def get_article(article_id: str) -> str:
        async with session_scope() as session:
            result = await McpService(session).get_article(_user_id(), article_id)
        return json.dumps(result, ensure_ascii=False)

    # The FastMCP handler lives at its default path ``/mcp``. We expose the whole
    # app as a root-level catch-all mount (see main.py) and let the guard own
    # exactly ``/mcp`` and ``/mcp/`` — so both spellings work with no redirect,
    # and every other path 404s normally instead of being swallowed by the mount.
    streamable_app = mcp.streamable_http_app()
    asgi_app = ServiceAccountAuthMiddleware(
        streamable_app, mcp.settings.streamable_http_path
    )

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp.session_manager.run():
            yield

    return mcp, asgi_app, lifespan


mcp, mcp_asgi_app, mcp_lifespan = build_mcp_server()
