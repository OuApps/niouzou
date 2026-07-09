"""Curated OpenRouter models catalogue (E8-S3).

The admin "OpenRouter model" dropdown needs a short, filtered list — the raw
``GET /api/v1/models`` reply is hundreds of entries spanning embeddings,
multimodal image models, and unaffordable large flagships. This service
applies the price + capability filters defined in EPICS.md (E8-S3) and
caches the result for an hour so opening the admin screen doesn't hammer
OpenRouter.
"""

import logging
import time

import httpx

from niouzou.config import get_settings
from niouzou.errors import APIError
from niouzou.schemas.admin import AdminModel

logger = logging.getLogger("niouzou.admin_models")

# Caps from EPICS.md (E8-S3): cheap text-to-text instruct models only.
# Enrichment runs on every article, so the price gate is tight. The chat
# (E21-S7) is an on-demand, per-question usage where reasoning quality
# matters — its caps are much wider so reasoning-tier models (DeepSeek R1,
# o4-mini, Sonnet-class…) actually appear in the selector, while the
# unaffordable flagship tier stays out.
_PRICE_CAPS_PER_M = {
    "enrichment": (0.10, 0.40),  # (input, output)
    "chat": (5.0, 20.0),
}
_MIN_CONTEXT_LENGTH = 8000

# In-process cache: one entry per usage profile, shared across requests on
# this worker. Replaced atomically on refresh so concurrent readers don't
# see a half list.
_CACHE_TTL_SECONDS = 3600.0
_cache: dict[str, tuple[float, list[AdminModel]]] = {}


def _price_per_m(raw: object) -> float:
    """OpenRouter prices come as strings ``$/token``; convert to ``$/1M``."""
    if raw is None:
        return 0.0
    try:
        return float(raw) * 1_000_000
    except (TypeError, ValueError):
        return 0.0


def _accepts_text_to_text(arch: dict | None) -> bool:
    """True when the model takes text in and produces text out."""
    if not isinstance(arch, dict):
        # Best effort: keep the model so a non-standard catalogue entry isn't
        # silently dropped.
        return True
    input_modalities = arch.get("input_modalities") or arch.get("modality") or []
    output_modalities = arch.get("output_modalities") or []
    if isinstance(input_modalities, str):
        input_modalities = [input_modalities]
    if isinstance(output_modalities, str):
        output_modalities = [output_modalities]
    # "text" must appear on both sides; reject if explicitly image/audio only.
    has_text_in = not input_modalities or "text" in input_modalities or "text+image" in input_modalities or "text->text" in input_modalities
    has_text_out = not output_modalities or "text" in output_modalities or "text->text" in output_modalities
    return has_text_in and has_text_out


def _looks_chat_capable(item: dict) -> bool:
    """Reject completion-only base models — we need instruct/chat behaviour."""
    id_ = (item.get("id") or "").lower()
    description = (item.get("description") or "").lower()
    context_length = int(item.get("context_length") or 0)
    keywords = ("instruct", "chat", "it", "sft", "rlhf", "assistant")
    if any(k in id_ for k in keywords) or any(k in description for k in keywords):
        return True
    # Long-context catalogue entries are nearly always chat-tuned today.
    return context_length >= _MIN_CONTEXT_LENGTH


def _passes_filters(item: dict, usage: str) -> bool:
    pricing = item.get("pricing") or {}
    input_price = _price_per_m(pricing.get("prompt"))
    output_price = _price_per_m(pricing.get("completion"))
    max_input, max_output = _PRICE_CAPS_PER_M[usage]
    if input_price > max_input:
        return False
    if output_price > max_output:
        return False
    if not _accepts_text_to_text(item.get("architecture")):
        return False
    if not _looks_chat_capable(item):
        return False
    return True


def _capabilities(item: dict) -> tuple[bool, bool]:
    """(reasoning, web_search) read from the catalogue entry (E21-S7).

    ``supported_parameters`` advertises reasoning support; native web search
    shows up either as a ``web_search`` price or as the
    ``web_search_options`` parameter. Any model can *also* search via
    OpenRouter's web plugin (the ``chat_web_search`` setting) — this flag
    only marks the ones with search built in.
    """
    params = item.get("supported_parameters") or []
    if not isinstance(params, list):
        params = []
    reasoning = "reasoning" in params or "include_reasoning" in params
    pricing = item.get("pricing") or {}
    web = "web_search_options" in params or _price_per_m(pricing.get("web_search")) > 0
    return reasoning, web


def _to_admin_model(item: dict) -> AdminModel:
    pricing = item.get("pricing") or {}
    reasoning, web_search = _capabilities(item)
    return AdminModel(
        id=item["id"],
        name=item.get("name") or item["id"],
        input_price_per_m=round(_price_per_m(pricing.get("prompt")), 4),
        output_price_per_m=round(_price_per_m(pricing.get("completion")), 4),
        context_length=int(item.get("context_length") or 0),
        reasoning=reasoning,
        web_search=web_search,
    )


async def fetch_models(
    api_key: str | None, usage: str = "enrichment"
) -> list[AdminModel]:
    """Hit the OpenRouter catalogue and apply the curation filters.

    ``usage`` selects the curation profile: ``"enrichment"`` (tight price
    caps — the historical E8-S3 list) or ``"chat"`` (E21-S7 — wider caps so
    reasoning-tier models appear, sorted reasoning-first).

    Raises ``APIError(424)`` when the key is missing — the caller surfaces
    that to the admin so they wire up a key before picking a model.
    """
    if usage not in _PRICE_CAPS_PER_M:
        raise APIError(422, "validation_error", f"Unknown usage: {usage}")
    cached = _cache.get(usage)
    if cached is not None:
        cached_at, items = cached
        if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
            return items

    if not api_key:
        raise APIError(
            424,
            "openrouter_key_missing",
            "OpenRouter API key is not configured",
        )

    settings = get_settings()
    url = f"{settings.openrouter_base_url.rstrip('/')}/models"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    if resp.status_code >= 400:
        logger.warning(
            "admin_models: OpenRouter returned %s — %s",
            resp.status_code,
            resp.text[:200],
        )
        raise APIError(
            502,
            "openrouter_unavailable",
            "OpenRouter catalogue could not be fetched",
        )

    payload = resp.json()
    raw = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise APIError(
            502,
            "openrouter_unavailable",
            "OpenRouter returned an unexpected payload",
        )

    curated = [
        _to_admin_model(item)
        for item in raw
        if isinstance(item, dict) and _passes_filters(item, usage)
    ]
    if usage == "chat":
        # Reasoning models first — that's what the chat selector is for.
        curated.sort(
            key=lambda m: (not m.reasoning, m.input_price_per_m, m.name.lower())
        )
    else:
        curated.sort(key=lambda m: (m.input_price_per_m, m.name.lower()))
    _cache[usage] = (time.monotonic(), curated)
    return curated


def reset_cache() -> None:
    """Test helper — clear the in-process cache between runs."""
    _cache.clear()
