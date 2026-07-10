"""Article chat tests (E21-S1/S2).

No test here ever talks to the real OpenRouter: the streaming path is mocked
with respx (same pattern as the Miniflux tests), and the prompt/guard logic
is exercised directly on ``ChatService``.
"""

import json

import pytest
import respx
from httpx import Response
from pydantic import ValidationError
from sqlalchemy import select

from niouzou.errors import APIError
from niouzou.models import LlmPrompt
from niouzou.models.llm_usage_log import LLMUsageLog
from niouzou.schemas.chat import ChatMessage, ChatRequest
from niouzou.services.chat_service import (
    CHAT_PROMPT_NAME,
    DEFAULT_CHAT_INSTRUCTION,
    ChatService,
    build_system_prompt,
)
from niouzou.services.settings_service import SettingsService
from tests.factories import make_article, make_source, make_user

# ── build_system_prompt (pure) ──────────────────────────────────────────────


def test_prompt_includes_summary_and_content():
    prompt = build_system_prompt(
        instruction=DEFAULT_CHAT_INSTRUCTION,
        title="Why Rust is eating C++",
        source_name="The Pragmatic Engineer",
        summary_executive="- Rust adoption up 40%",
        content="Long body " * 10,
        max_chars=2500,
    )
    assert "Why Rust is eating C++" in prompt
    assert "The Pragmatic Engineer" in prompt
    assert "- Rust adoption up 40%" in prompt
    assert "Long body" in prompt


def test_prompt_truncates_content_to_budget():
    summary = "S" * 100
    body = "x" * 5000
    prompt = build_system_prompt(
        instruction=DEFAULT_CHAT_INSTRUCTION,
        title="T",
        source_name="Src",
        summary_executive=summary,
        content=body,
        max_chars=600,
    )
    # Content budget = max_chars - len(summary) = 500, plus the ellipsis.
    assert "x" * 500 + "…" in prompt
    assert "x" * 501 not in prompt
    # The summary is never truncated.
    assert summary in prompt


def test_prompt_falls_back_to_summary_only():
    prompt = build_system_prompt(
        instruction=DEFAULT_CHAT_INSTRUCTION,
        title="T",
        source_name="Src",
        summary_executive="just the summary",
        content=None,
        max_chars=2500,
    )
    assert "just the summary" in prompt
    assert "Article content" not in prompt


def test_prompt_survives_no_summary_no_content():
    prompt = build_system_prompt(
        instruction=DEFAULT_CHAT_INSTRUCTION,
        title="T", source_name="Src", summary_executive=None, content=None,
        max_chars=2500,
    )
    assert "Title: T" in prompt
    assert "Summary" not in prompt
    assert "Article content" not in prompt


# ── ChatRequest bounds ──────────────────────────────────────────────────────


def test_chat_request_rejects_assistant_last_turn():
    with pytest.raises(ValidationError, match="last message must be a user turn"):
        ChatRequest(
            messages=[
                ChatMessage(role="user", content="hi"),
                ChatMessage(role="assistant", content="hello"),
            ]
        )


def test_chat_request_rejects_oversized_thread():
    with pytest.raises(ValidationError, match="thread too long"):
        ChatRequest(
            messages=[
                ChatMessage(role="user", content="x" * 4000) for _ in range(7)
            ]
        )


def test_chat_request_rejects_empty_thread():
    with pytest.raises(ValidationError):
        ChatRequest(messages=[])


# ── ChatService.prepare — guards + model resolution ─────────────────────────


def _turn(content="What is this about?"):
    return [ChatMessage(role="user", content=content)]


async def test_prepare_404_on_unknown_article(db_session):
    import uuid

    user = await make_user(db_session)
    with pytest.raises(APIError) as exc:
        await ChatService(db_session).prepare(user.id, uuid.uuid4(), _turn())
    assert exc.value.status_code == 404


async def test_prepare_403_on_foreign_article(db_session):
    owner = await make_user(db_session, email="owner@test.dev")
    intruder = await make_user(db_session, email="intruder@test.dev")
    source = await make_source(db_session, owner)
    article = await make_article(db_session, source)

    with pytest.raises(APIError) as exc:
        await ChatService(db_session).prepare(intruder.id, article.id, _turn())
    assert exc.value.status_code == 403


async def test_prepare_409_without_api_key(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)

    with pytest.raises(APIError) as exc:
        await ChatService(db_session).prepare(user.id, article.id, _turn())
    assert exc.value.status_code == 409
    assert exc.value.error == "ai_disabled"


async def test_prepare_builds_context_with_article_and_thread(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user, name="The Pragmatic Engineer")
    article = await make_article(db_session, source, title="Rust vs C++")
    article.summary_executive = "- Rust adoption up 40%"
    article.content = "Full crawled body."
    await db_session.flush()

    svc = SettingsService(db_session)
    await svc.set("openrouter_api_key", "sk-test")
    await svc.set("chat_model", "anthropic/claude-sonnet-5")
    await db_session.commit()

    ctx = await ChatService(db_session).prepare(
        user.id, article.id, _turn("Tell me more")
    )
    assert ctx.model == "anthropic/claude-sonnet-5"
    assert ctx.api_key == "sk-test"
    system, *thread = ctx.payload_messages
    assert system["role"] == "system"
    assert "Rust vs C++" in system["content"]
    assert "- Rust adoption up 40%" in system["content"]
    assert "Full crawled body." in system["content"]
    assert thread == [{"role": "user", "content": "Tell me more"}]


async def test_chat_model_falls_back_to_enrichment_model(db_session):
    """Unset chat_model follows the *effective* openrouter_model (E21-S1)."""
    svc = SettingsService(db_session)
    # Env default (no overrides at all).
    assert await svc.get("chat_model") == "google/gemma-4-26b-a4b-it:free"
    assert (await svc.get_effective()).chat_model == "google/gemma-4-26b-a4b-it:free"

    # DB-overridden enrichment model is honoured too.
    await svc.set("openrouter_model", "openai/gpt-4o")
    await db_session.commit()
    assert await svc.get("chat_model") == "openai/gpt-4o"
    assert (await svc.get_effective()).chat_model == "openai/gpt-4o"

    # An explicit chat_model override wins…
    await svc.set("chat_model", "anthropic/claude-sonnet-5")
    await db_session.commit()
    assert await svc.get("chat_model") == "anthropic/claude-sonnet-5"
    assert (await svc.get_effective()).chat_model == "anthropic/claude-sonnet-5"

    # …and clearing it falls back again.
    await svc.set("chat_model", "")
    await db_session.commit()
    assert await svc.get("chat_model") == "openai/gpt-4o"


# ── ChatService.stream — SSE relay + usage log ──────────────────────────────


def _openrouter_sse(*deltas, usage=None):
    lines = [
        "data: "
        + json.dumps({"choices": [{"delta": {"content": d}}]})
        + "\n\n"
        for d in deltas
    ]
    final: dict = {"choices": [{"delta": {}}]}
    if usage is not None:
        final["usage"] = usage
    lines.append("data: " + json.dumps(final) + "\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _parse_events(chunks):
    events = []
    for chunk in chunks:
        lines = chunk.strip().split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


async def _stream_ctx(db_session):
    from niouzou.services.chat_service import ChatContext

    return ChatService(db_session), ChatContext(
        api_key="sk-test",
        model="test/chat-model",
        payload_messages=[{"role": "user", "content": "hi"}],
    )


@respx.mock
async def test_stream_relays_tokens_and_logs_usage(db_session):
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=_openrouter_sse(
                "Bon",
                "jour",
                usage={"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.00042},
            ),
            headers={"content-type": "text/event-stream"},
        )
    )
    service, ctx = await _stream_ctx(db_session)
    events = _parse_events([chunk async for chunk in service.stream(ctx)])

    assert events[0] == ("token", {"delta": "Bon"})
    assert events[1] == ("token", {"delta": "jour"})
    assert events[-1] == (
        "done",
        {"model": "test/chat-model", "prompt_tokens": 100, "completion_tokens": 20},
    )

    row = (await db_session.execute(select(LLMUsageLog))).scalar_one()
    assert row.model == "test/chat-model"
    assert row.usage == "chat"
    assert row.cost_usd == pytest.approx(0.00042)
    assert row.prompt_tokens == 100
    assert row.completion_tokens == 20


@respx.mock
async def test_stream_upstream_http_error_yields_error_event(db_session):
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(402, json={"error": "insufficient credits"})
    )
    service, ctx = await _stream_ctx(db_session)
    events = _parse_events([chunk async for chunk in service.stream(ctx)])

    assert len(events) == 1
    assert events[0][0] == "error"
    assert events[0][1]["error"] == "upstream_error"
    # No usage row on failure.
    assert (await db_session.execute(select(LLMUsageLog))).first() is None


# ── E21-S8 — editable chat instruction + per-usage cost split ───────────────


async def test_prepare_uses_admin_edited_instruction(db_session):
    """The chat.system row (Admin → LLM Prompts) drives the system prompt."""
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await SettingsService(db_session).set("openrouter_api_key", "sk-test")

    row = await db_session.get(LlmPrompt, CHAT_PROMPT_NAME)
    original = row.body if row else None
    if row is None:
        db_session.add(LlmPrompt(name=CHAT_PROMPT_NAME, body="x"))
        await db_session.flush()
        row = await db_session.get(LlmPrompt, CHAT_PROMPT_NAME)
    row.body = "Tu es un assistant pirate. Réponds en argot."
    await db_session.commit()

    try:
        ctx = await ChatService(db_session).prepare(user.id, article.id, _turn())
        system = ctx.payload_messages[0]["content"]
        assert system.startswith("Tu es un assistant pirate.")
        # The article context is still appended by code, whatever the edit.
        assert "Title:" in system
    finally:
        # llm_prompts is not truncated between tests — restore the seed.
        if original is not None:
            row.body = original
            await db_session.commit()


async def test_llm_cost_split_by_usage(db_session):
    from niouzou.services.stats_service import StatsService

    db_session.add_all(
        [
            LLMUsageLog(model="m", usage="enrichment", cost_usd=0.03),
            LLMUsageLog(model="m", usage="chat", cost_usd=0.01),
            LLMUsageLog(model="m", usage="chat", cost_usd=0.02),
        ]
    )
    await db_session.commit()

    stats = await StatsService(db_session)._llm_cost_aggregates()
    for window in stats.windows:  # all rows are 'now', every window sees them
        assert window.cost_usd == pytest.approx(0.06)
        assert window.enrichment_cost_usd == pytest.approx(0.03)
        assert window.chat_cost_usd == pytest.approx(0.03)


# ── E21-S7 — chat model curation + web search ───────────────────────────────


def _catalogue_item(
    id_,
    *,
    # OpenRouter prices are $/token: 5e-8 = $0.05/M — under the enrichment cap.
    prompt="0.00000005",
    completion="0.0000002",
    supported=None,
    web_price=None,
):
    pricing = {"prompt": prompt, "completion": completion}
    if web_price is not None:
        pricing["web_search"] = web_price
    return {
        "id": id_,
        "name": id_,
        "context_length": 32000,
        "description": "chat model",
        "pricing": pricing,
        "supported_parameters": supported or [],
    }


@respx.mock
async def test_models_chat_usage_widens_caps_and_flags_capabilities():
    from niouzou.services import admin_models_service as ams

    ams.reset_cache()
    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    # Cheap model, fits both curations.
                    _catalogue_item("cheap/instruct"),
                    # Reasoning-tier: $3/M in — above the enrichment cap
                    # (0.10) but within the chat cap (5.0).
                    _catalogue_item(
                        "big/reasoner",
                        prompt="0.000003",
                        completion="0.000015",
                        supported=["reasoning"],
                    ),
                    # Native web search via pricing.
                    _catalogue_item("sonar/online", web_price="0.000004"),
                ]
            },
        )
    )

    enrichment = await ams.fetch_models("sk-test", usage="enrichment")
    assert [m.id for m in enrichment] == ["cheap/instruct", "sonar/online"]

    chat = await ams.fetch_models("sk-test", usage="chat")
    # Reasoning models sort first in the chat curation.
    assert [m.id for m in chat] == [
        "big/reasoner",
        "cheap/instruct",
        "sonar/online",
    ]
    by_id = {m.id: m for m in chat}
    assert by_id["big/reasoner"].reasoning is True
    assert by_id["big/reasoner"].web_search is False
    assert by_id["sonar/online"].web_search is True
    assert by_id["cheap/instruct"].reasoning is False
    ams.reset_cache()


async def test_chat_web_search_setting_bool_round_trip(db_session):
    svc = SettingsService(db_session)
    # Env default.
    assert await svc.get("chat_web_search") is False
    assert (await svc.get_effective()).chat_web_search is False

    await svc.set("chat_web_search", True)
    await db_session.commit()
    assert await svc.get("chat_web_search") is True
    assert (await svc.get_effective()).chat_web_search is True

    await svc.set("chat_web_search", False)
    await db_session.commit()
    assert await svc.get("chat_web_search") is False


@respx.mock
async def test_stream_sends_web_plugin_when_enabled(db_session):
    from niouzou.services.chat_service import ChatContext

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=_openrouter_sse("ok"),
            headers={"content-type": "text/event-stream"},
        )
    )
    service = ChatService(db_session)

    ctx = ChatContext(
        api_key="sk", model="m", payload_messages=[], web_search=True
    )
    [c async for c in service.stream(ctx)]
    assert json.loads(route.calls[0].request.content)["plugins"] == [{"id": "web"}]

    ctx_off = ChatContext(api_key="sk", model="m", payload_messages=[])
    [c async for c in service.stream(ctx_off)]
    assert "plugins" not in json.loads(route.calls[1].request.content)


# ── Endpoint wiring — full HTTP round-trip through the app ──────────────────
# httpx.AsyncClient + ASGITransport (the test_pipeline_runs.py pattern —
# TestClient would corrupt the shared asyncpg pool). respx only patches the
# *default* transports, so it mocks the app's outbound OpenRouter call while
# leaving the explicit ASGITransport untouched.


async def _app_client(user_id):
    import httpx

    from niouzou.deps import get_current_user
    from niouzou.main import app

    class _FakeUser:
        id = user_id
        is_admin = False

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    transport = httpx.ASGITransport(app=app)
    return app, httpx.AsyncClient(transport=transport, base_url="http://t")


@respx.mock
async def test_chat_endpoint_streams_sse(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, title="Rust vs C++")
    await SettingsService(db_session).set("openrouter_api_key", "sk-test")
    await db_session.commit()

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=_openrouter_sse("Hello", usage={"prompt_tokens": 1, "completion_tokens": 1}),
            headers={"content-type": "text/event-stream"},
        )
    )

    app, client = await _app_client(user.id)
    try:
        async with client:
            resp = await client.post(
                f"/api/v1/articles/{article.id}/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.text
        assert 'event: token\ndata: {"delta": "Hello"}' in body
        assert "event: done" in body
    finally:
        app.dependency_overrides.clear()


async def test_chat_endpoint_422_on_assistant_last_turn(db_session):
    user = await make_user(db_session)
    await db_session.commit()

    app, client = await _app_client(user.id)
    try:
        async with client:
            resp = await client.post(
                "/api/v1/articles/00000000-0000-0000-0000-000000000000/chat",
                json={"messages": [{"role": "assistant", "content": "hi"}]},
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_chat_endpoint_409_without_api_key(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source)
    await db_session.commit()

    app, client = await _app_client(user.id)
    try:
        async with client:
            resp = await client.post(
                f"/api/v1/articles/{article.id}/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert resp.status_code == 409
        assert resp.json()["error"] == "ai_disabled"
    finally:
        app.dependency_overrides.clear()


@respx.mock
async def test_stream_missing_usage_still_completes(db_session):
    """A stream without a usage chunk logs a zero-cost row (best-effort)."""
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=_openrouter_sse("ok"),
            headers={"content-type": "text/event-stream"},
        )
    )
    service, ctx = await _stream_ctx(db_session)
    events = _parse_events([chunk async for chunk in service.stream(ctx)])

    assert events[-1][0] == "done"
    row = (await db_session.execute(select(LLMUsageLog))).scalar_one()
    assert row.cost_usd == 0.0
