"""ForwardedHostMiddleware — promote the trusted X-Edge-Host to the ASGI Host.

Behind the Cloudflare → Railway edge, Railway rewrites Host / X-Forwarded-Host
to the internal *.up.railway.app origin; the real public host arrives in
X-Edge-Host. These tests exercise the middleware in isolation over a tiny
capture app, so no DB / HTTP is needed.
"""

from niouzou.middleware import ForwardedHostMiddleware


async def _capture_host(headers: list[tuple[bytes, bytes]]) -> bytes | None:
    """Run the middleware over `headers` and return the Host the inner app sees."""
    seen: dict[str, bytes | None] = {"host": None}

    async def inner(scope, receive, send):
        seen["host"] = dict(scope["headers"]).get(b"host")

    app = ForwardedHostMiddleware(inner)
    scope = {"type": "http", "headers": headers}
    await app(scope, None, None)
    return seen["host"]


async def test_x_edge_host_overrides_internal_host():
    host = await _capture_host(
        [
            (b"host", b"api-production-1eb1.up.railway.app"),
            (b"x-edge-host", b"api-niouzou.galaxou.com"),
        ]
    )
    assert host == b"api-niouzou.galaxou.com"


async def test_no_edge_header_is_a_noop():
    host = await _capture_host([(b"host", b"localhost:8000")])
    assert host == b"localhost:8000"


async def test_edge_host_does_not_duplicate_host_header():
    """Exactly one Host header survives — the public one, not the internal."""
    captured: dict[str, list] = {"headers": []}

    async def inner(scope, receive, send):
        captured["headers"] = scope["headers"]

    app = ForwardedHostMiddleware(inner)
    scope = {
        "type": "http",
        "headers": [
            (b"host", b"internal.up.railway.app"),
            (b"x-edge-host", b"api-niouzou.galaxou.com"),
        ],
    }
    await app(scope, None, None)
    hosts = [v for (k, v) in captured["headers"] if k == b"host"]
    assert hosts == [b"api-niouzou.galaxou.com"]


async def test_non_http_scope_passes_through_untouched():
    """A websocket/lifespan scope must not be mutated (no Host semantics)."""
    seen: dict[str, object] = {}

    async def inner(scope, receive, send):
        seen["scope"] = scope

    app = ForwardedHostMiddleware(inner)
    scope = {"type": "lifespan", "headers": []}
    await app(scope, None, None)
    assert seen["scope"] is scope
