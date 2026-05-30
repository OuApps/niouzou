"""Thin synchronous client over the OpenRouter chat-completions API.

OpenRouter is optional: the whole system works without it (TF-IDF fallback).
When ``OPENROUTER_API_KEY`` is set, the enrichment cron uses it for summaries
and ``AIKeywordScorer`` uses it for keyword extraction.

Why synchronous (unlike ``MinifluxClient``)?
    The scorer contract ``BaseScorer.extract_keywords`` is synchronous — it is
    shared with the pure-Python ``TFIDFScorer`` — so the LLM client it depends
    on must be callable without ``await``. The enrichment cron is a sequential
    batch job, so a blocking HTTP call here costs nothing in practice.

API reference: https://openrouter.ai/docs/api-reference/chat-completion
Auth: ``Authorization: Bearer <OPENROUTER_API_KEY>``.
"""

import json
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from niouzou.config import get_settings

T = TypeVar("T")


class OpenRouterError(RuntimeError):
    """Raised when an OpenRouter call ultimately fails (transport or parsing).

    The enrichment cron catches this and falls back to TF-IDF, so a flaky LLM
    never blocks the pipeline.
    """


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                # Optional attribution headers OpenRouter surfaces in dashboards.
                "HTTP-Referer": "https://github.com/niouzou",
                "X-Title": "Niouzou",
            },
            timeout=timeout,
        )

    @classmethod
    def from_settings(cls) -> "OpenRouterClient | None":
        """Build a client from config, or ``None`` when no API key is set."""
        settings = get_settings()
        if not settings.openrouter_api_key:
            return None
        return cls(
            settings.openrouter_api_key,
            settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            timeout=settings.openrouter_timeout,
        )

    @classmethod
    def from_overrides(
        cls, api_key: str | None, model: str
    ) -> "OpenRouterClient | None":
        """Build a client using runtime-resolved values (E8-S2).

        ``cron_enrich`` calls this with values from ``SettingsService`` so a
        live ``OPENROUTER_MODEL`` change picks up on the next run without a
        restart. Base URL and timeout still come from env (no admin override).
        """
        if not api_key:
            return None
        settings = get_settings()
        return cls(
            api_key,
            model,
            base_url=settings.openrouter_base_url,
            timeout=settings.openrouter_timeout,
        )

    def __enter__(self) -> "OpenRouterClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def complete(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        """Single chat completion. Returns the assistant message content."""
        resp = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(f"Unexpected OpenRouter response shape: {data!r}") from exc

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        parse: Callable[[Any], T],
        retries: int = 1,
        temperature: float = 0.2,
    ) -> T:
        """Complete, extract JSON from the reply, and validate it via ``parse``.

        A malformed reply (bad transport, non-JSON content, or a structure
        ``parse`` rejects) is retried ``retries`` times before raising
        ``OpenRouterError`` — matching E5-S2's "retried once, then fall back".
        """
        last_exc: Exception | None = None
        for _ in range(retries + 1):
            try:
                content = self.complete(system=system, user=user, temperature=temperature)
                return parse(extract_json(content))
            except (
                httpx.HTTPError,
                OpenRouterError,
                json.JSONDecodeError,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:
                last_exc = exc
        raise OpenRouterError(
            f"OpenRouter call failed after {retries + 1} attempt(s): {last_exc}"
        ) from last_exc


def extract_json(content: str) -> Any:
    """Best-effort JSON extraction from an LLM reply.

    Models often wrap JSON in prose or ```json fences```, so we try a direct
    parse first, then fall back to the outermost ``{...}`` / ``[...]`` span.
    """
    text = content.strip()
    if text.startswith("```"):
        # Strip a ```json ... ``` (or bare ```) fence.
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to the widest bracketed span, anchored on whichever of '{' / '['
    # appears first — so a list-of-objects wrapped in prose isn't mistaken for
    # its first inner object.
    spans = []
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            spans.append((start, text[start : end + 1]))
    for _, snippet in sorted(spans):
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No JSON object found in LLM reply: {content[:200]!r}")
