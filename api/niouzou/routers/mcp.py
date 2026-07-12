"""MCP Streamable HTTP endpoint (E22-S3).

A hand-rolled, stateless implementation of the Model Context Protocol's
Streamable HTTP transport: JSON-RPC 2.0 over ``POST /mcp``, authenticated with
a service account key (``Authorization: Bearer nzk_…``). The server replies in
``application/json`` only — it never opens a server-initiated SSE stream — which
is spec-compliant for a session-less server. See ``services/mcp_service.py`` for
the tool implementations.

Kept deliberately small: routers stay thin, business logic lives in
``McpService``, and there's no session manager / lifespan to wire (unlike the
official SDK), so it drops cleanly into the existing FastAPI app and tests.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from niouzou.deps import SessionDep
from niouzou.errors import unauthorized
from niouzou.models import User
from niouzou.services.mcp_service import TOOLS, McpService, McpToolError
from niouzou.services.service_account_service import ServiceAccountService

router = APIRouter(tags=["mcp"])

# The protocol revision we implement. We echo back the client's requested
# version when it sends one (maximising client compatibility), falling back to
# this when it doesn't.
SUPPORTED_PROTOCOL_VERSION = "2025-06-18"

SERVER_INFO = {"name": "niouzou", "version": "0.1.0"}

# JSON-RPC 2.0 error codes we emit.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


async def get_mcp_user(request: Request, session: SessionDep) -> User:
    """Resolve the service account key on the request to its owning user."""
    token = _bearer_token(request)
    user = await ServiceAccountService(session).authenticate(token)
    if user is None:
        raise unauthorized("Invalid or revoked service account key")
    return user


McpUser = Annotated[User, Depends(get_mcp_user)]


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


async def _handle_message(
    msg: Any, user: User, service: McpService
) -> dict | None:
    """Handle one JSON-RPC message. Returns a response, or ``None`` for a
    notification (a message with no ``id``)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Invalid JSON-RPC message")

    msg_id = msg.get("id")
    is_notification = "id" not in msg
    method = msg.get("method")
    params = msg.get("params") or {}

    # Notifications (initialized, cancelled…) get no response body.
    if is_notification:
        return None

    if method == "initialize":
        requested = params.get("protocolVersion")
        return _result(
            msg_id,
            {
                "protocolVersion": (
                    requested
                    if isinstance(requested, str) and requested
                    else SUPPORTED_PROTOCOL_VERSION
                ),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )

    if method == "ping":
        return _result(msg_id, {})

    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not name:
            return _error(msg_id, INVALID_PARAMS, "Missing tool name")
        if not isinstance(arguments, dict):
            return _error(msg_id, INVALID_PARAMS, "`arguments` must be an object")
        try:
            payload = await service.dispatch(user.id, name, arguments)
        except McpToolError as exc:
            # Tool-level failures are results (isError), not protocol errors.
            return _result(
                msg_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        return _result(
            msg_id,
            {
                "content": [
                    {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
                ],
                "isError": False,
            },
        )

    return _error(msg_id, METHOD_NOT_FOUND, f"Unknown method: {method}")


@router.post("/mcp")
async def mcp_endpoint(
    request: Request, user: McpUser, session: SessionDep
) -> Response:
    raw = await request.body()
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=200, content=_error(None, PARSE_ERROR, "Parse error")
        )

    service = McpService(session)

    # A batch is an array of messages; a single message is a bare object.
    if isinstance(body, list):
        if not body:
            return JSONResponse(
                status_code=200,
                content=_error(None, INVALID_REQUEST, "Empty batch"),
            )
        responses = [
            r
            for msg in body
            if (r := await _handle_message(msg, user, service)) is not None
        ]
        # Only notifications → 202 Accepted, no body (per the transport spec).
        if not responses:
            return Response(status_code=202)
        return JSONResponse(status_code=200, content=responses)

    response = await _handle_message(body, user, service)
    if response is None:
        return Response(status_code=202)
    return JSONResponse(status_code=200, content=response)
