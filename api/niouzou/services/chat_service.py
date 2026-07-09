"""Article chat business logic (E21-S2).

``POST /articles/{id}/chat`` relays a conversation to OpenRouter with the
article injected as system context. Unlike enrichment — a sequential batch on
the worker, served by the *synchronous* ``OpenRouterClient`` — the chat is a
live call from the API process, so it uses its own **async** streaming path
(plain ``httpx.AsyncClient`` on ``/chat/completions``); never import the sync
client (or anything torch-adjacent) here, uvicorn must stay light (EPIC 20).

Flow: the router calls ``prepare`` first (all guards fail there as regular
JSON errors — 403/404/409 — before any byte is streamed), then wraps
``stream`` in a ``StreamingResponse``. SSE contract:

* ``event: token``  → ``{"delta": "<text fragment>"}``
* ``event: done``   → ``{"model": ..., "prompt_tokens": n, "completion_tokens": n}``
* ``event: error``  → ``{"error": "upstream_error", "message": ...}`` (mid-stream
  failures only — the HTTP status is already 200 by then)

Cost accounting reuses ``llm_usage_log`` (E10-S7) so chat spend shows up in
the System panel next to enrichment. OpenRouter is asked to include usage in
the final stream chunk (``usage: {"include": true}``) — no deferred
``/generation`` lookup needed (that endpoint 404s for a few seconds after a
completion, see E17-S1).
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi import status
from sqlalchemy import select

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.errors import APIError, not_found
from niouzou.models import Article, Source
from niouzou.models.llm_usage_log import LLMUsageLog
from niouzou.schemas.chat import ChatMessage
from niouzou.services.settings_service import SettingsService

logger = logging.getLogger("niouzou.chat")

# The article context injected as the system prompt. Kept as a module
# constant for v1 — promote it to the admin-editable ``llm_prompts`` table
# (E13-S2) if operators ask to tune it.
_SYSTEM_TEMPLATE = """\
You are Niouzou's reading assistant. The user is reading the news article \
below and wants to discuss it: ask for clarifications, dig into a point, or \
broaden the topic. Ground your answers in the article; when the user goes \
beyond it, you may use general knowledge but say you are doing so. Be \
concise. Answer in the language the user writes in.

Title: {title}
Source: {source_name}
{summary_block}{content_block}"""


def build_system_prompt(
    *,
    title: str,
    source_name: str,
    summary_executive: str | None,
    content: str | None,
    max_chars: int,
) -> str:
    """Assemble the system prompt, capping summary ⊕ content at ``max_chars``.

    Reuses the enrichment input budget (``enrichment_input_max_chars``) so the
    operator tunes one knob for "how much article do we send to the LLM".
    The summary is short and always included whole; the crawled content
    absorbs the truncation. Falls back gracefully when either is missing.
    """
    summary = (summary_executive or "").strip()
    body = (content or "").strip()

    summary_block = f"\nSummary:\n{summary}\n" if summary else ""
    content_budget = max(0, max_chars - len(summary))
    if body and content_budget > 0:
        excerpt = body[:content_budget]
        suffix = "…" if len(body) > content_budget else ""
        content_block = f"\nArticle content (may be truncated):\n{excerpt}{suffix}\n"
    else:
        content_block = ""

    return _SYSTEM_TEMPLATE.format(
        title=title,
        source_name=source_name,
        summary_block=summary_block,
        content_block=content_block,
    )


@dataclass(slots=True)
class ChatContext:
    """Everything ``stream`` needs, resolved by ``prepare``."""

    api_key: str
    model: str
    payload_messages: list[dict[str, str]]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def prepare(
        self,
        user_id: uuid.UUID,
        article_id: uuid.UUID,
        messages: list[ChatMessage],
    ) -> ChatContext:
        """Run every guard and build the OpenRouter payload.

        Raises (as regular JSON errors, before any streaming starts):

        * 404 — no article with that id (same uniform surface as score-debug);
        * 403 — article belongs to another user's source;
        * 409 ``ai_disabled`` — no OpenRouter API key configured.
        """
        row = (
            await self.session.execute(
                select(
                    Article.title,
                    Article.summary_executive,
                    Article.content,
                    Source.user_id,
                    Source.name.label("source_name"),
                )
                .join(Source, Source.id == Article.source_id)
                .where(Article.id == article_id)
            )
        ).first()
        if row is None:
            raise not_found("Article not found")
        if row.user_id != user_id:
            raise APIError(
                status.HTTP_403_FORBIDDEN, "forbidden", "Article not accessible"
            )

        effective = await SettingsService(self.session).get_effective()
        if not effective.openrouter_api_key:
            raise APIError(
                status.HTTP_409_CONFLICT,
                "ai_disabled",
                "Article chat requires an OpenRouter API key.",
            )

        system = build_system_prompt(
            title=row.title,
            source_name=row.source_name,
            summary_executive=row.summary_executive,
            content=row.content,
            max_chars=effective.enrichment_input_max_chars,
        )
        return ChatContext(
            api_key=effective.openrouter_api_key,
            model=effective.chat_model,
            payload_messages=[
                {"role": "system", "content": system},
                *({"role": m.role, "content": m.content} for m in messages),
            ],
        )

    async def stream(self, ctx: ChatContext) -> AsyncIterator[str]:
        """Relay the OpenRouter SSE stream as our own token/done/error events.

        Runs inside a ``StreamingResponse`` — the request session is still
        open (dependency teardown happens after the response finishes), so the
        usage row is written on the same session and committed by the normal
        request boundary. Mid-stream failures can't change the HTTP status
        anymore; they surface as an ``error`` event instead.
        """
        settings = get_settings()
        usage: dict | None = None
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.openrouter_timeout)
            ) as client:
                async with client.stream(
                    "POST",
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {ctx.api_key}",
                        # Same attribution headers as the sync client.
                        "HTTP-Referer": "https://github.com/niouzou",
                        "X-Title": "Niouzou",
                    },
                    json={
                        "model": ctx.model,
                        "messages": ctx.payload_messages,
                        "stream": True,
                        # Ask OpenRouter to append usage (incl. cost) to the
                        # final chunk — spares the deferred /generation lookup.
                        "usage": {"include": True},
                    },
                ) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode(errors="replace")
                        logger.warning(
                            "chat: OpenRouter returned %s — %.300s",
                            response.status_code,
                            detail,
                        )
                        yield _sse(
                            "error",
                            {
                                "error": "upstream_error",
                                "message": f"OpenRouter returned {response.status_code}",
                            },
                        )
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            # SSE comments (': OPENROUTER PROCESSING') & blanks.
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                        for choice in chunk.get("choices") or []:
                            delta = (choice.get("delta") or {}).get("content")
                            if delta:
                                yield _sse("token", {"delta": delta})
        except httpx.HTTPError as exc:
            logger.warning("chat: OpenRouter stream failed — %s", exc)
            yield _sse(
                "error",
                {"error": "upstream_error", "message": "OpenRouter unreachable"},
            )
            return

        prompt_tokens = int((usage or {}).get("prompt_tokens") or 0)
        completion_tokens = int((usage or {}).get("completion_tokens") or 0)
        await self._log_usage(ctx.model, usage, prompt_tokens, completion_tokens)
        yield _sse(
            "done",
            {
                "model": ctx.model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )

    async def _log_usage(
        self,
        model: str,
        usage: dict | None,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Append the chat completion to ``llm_usage_log`` (best-effort).

        A missing/malformed usage payload never breaks the chat — the row is
        simply logged with zero cost (same best-effort stance as E10-S7).
        """
        try:
            cost = float((usage or {}).get("cost") or 0.0)
            self.session.add(
                LLMUsageLog(
                    model=model,
                    cost_usd=cost,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            )
            await self.session.flush()
        except Exception:
            logger.debug("chat: usage log write failed", exc_info=True)
