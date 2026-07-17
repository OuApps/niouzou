"""ASGI middleware for running behind the Cloudflare → Railway reverse proxy.

**Why this exists.** Railway's own edge rewrites the inbound ``Host`` header
(and ``X-Forwarded-Host``) to the internal ``*.up.railway.app`` origin before a
request ever reaches the app, so neither can be trusted to reconstruct the
public URL. The Cloudflare proxy sitting in front of Railway therefore forwards
the real public host in a dedicated, un-rewritten header — ``X-Edge-Host``
(e.g. ``api-niouzou.galaxou.com``).

:class:`ForwardedHostMiddleware` promotes that header to the ASGI ``Host`` so
that ``request.url`` and the OpenAPI ``servers`` URL resolve to the public
custom domain instead of the internal Railway host. ``--proxy-headers`` already
covers the scheme via ``X-Forwarded-Proto``; this covers the host.

It is a **no-op when ``X-Edge-Host`` is absent** (local dev, self-hosters
without the Cloudflare edge), so the default behaviour is unchanged. We
deliberately do *not* fall back to ``X-Forwarded-Host``: behind Railway that
header carries the internal origin, which is exactly the value we are trying to
override.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

# The header the Cloudflare edge sets to the real public host. Kept as bytes to
# match the raw ASGI header representation without per-request encoding.
_EDGE_HOST_HEADER = b"x-edge-host"
_HOST_HEADER = b"host"


class ForwardedHostMiddleware:
    """Promote the trusted ``X-Edge-Host`` header to the ASGI ``Host``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = scope["headers"]
            public_host = dict(headers).get(_EDGE_HOST_HEADER)
            if public_host:
                # Drop the (internal) Host and re-append the public one.
                rebuilt = [(k, v) for (k, v) in headers if k != _HOST_HEADER]
                rebuilt.append((_HOST_HEADER, public_host))
                scope = {**scope, "headers": rebuilt}
        await self.app(scope, receive, send)
