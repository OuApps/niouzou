"""Tests for OpenRouterClient usage-log capture (E10-S7 / E17-S1).

``complete()`` only records the generation id; the $ cost is resolved later
via ``resolve_pending_usage()`` (called once per run from
``_flush_usage_log``). The cost comes from OpenRouter's ``/generation``
endpoint — the chat-completion response's ``usage`` field doesn't carry
``cost`` in this SDK version. The lookup is deferred to end of run because
``/generation`` 404s for a few seconds while OpenRouter finalises stats
(E17-S1). These tests build a real ``OpenRouterClient`` instance (bypassing
``__init__`` to avoid creating the real SDK transport) and stub ``_client``
with simple fakes.
"""

from types import SimpleNamespace

from niouzou.services.openrouter_client import OpenRouterClient, UsageRecord


def _client_with_fake_sdk(chat_send, get_generation=None):
    client = OpenRouterClient.__new__(OpenRouterClient)
    client._model = "test/model"
    client.usage_log = []
    client._pending_generations = []
    client._usage_retry_delay_s = 0.0
    client._client = SimpleNamespace(
        chat=SimpleNamespace(send=chat_send),
        generations=SimpleNamespace(
            get_generation=get_generation or (lambda id: None)
        ),
    )
    return client


def _chat_response(content="hello", generation_id="gen-1"):
    return SimpleNamespace(
        id=generation_id,
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def test_complete_records_usage_on_successful_generation_lookup():
    def get_generation(id):
        assert id == "gen-1"
        return SimpleNamespace(
            data=SimpleNamespace(
                total_cost=0.0042, tokens_prompt=100, tokens_completion=50
            )
        )

    client = _client_with_fake_sdk(
        chat_send=lambda **_kw: _chat_response(),
        get_generation=get_generation,
    )

    result = client.complete(system="sys", user="usr")

    # complete() only queues the id; cost is resolved at end of run.
    assert result == "hello"
    assert client.usage_log == []
    assert client._pending_generations == ["gen-1"]

    client.resolve_pending_usage()

    assert client.usage_log == [
        UsageRecord(
            model="test/model", cost_usd=0.0042, prompt_tokens=100, completion_tokens=50
        )
    ]
    assert client._pending_generations == []


def test_resolve_swallows_generation_lookup_failure():
    def get_generation(id):
        raise RuntimeError("404 not ready yet")

    client = _client_with_fake_sdk(
        chat_send=lambda **_kw: _chat_response(),
        get_generation=get_generation,
    )

    result = client.complete(system="sys", user="usr")
    client.resolve_pending_usage()

    assert result == "hello"
    assert client.usage_log == []


def test_resolve_retries_stragglers_before_giving_up():
    # First lookup 404s (stats not finalised), second succeeds — mimics the
    # end-of-run retry pass (E17-S1).
    calls = {"n": 0}

    def get_generation(id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("404 not ready yet")
        return SimpleNamespace(
            data=SimpleNamespace(
                total_cost=0.0042, tokens_prompt=100, tokens_completion=50
            )
        )

    client = _client_with_fake_sdk(
        chat_send=lambda **_kw: _chat_response(),
        get_generation=get_generation,
    )

    client.complete(system="sys", user="usr")
    client.resolve_pending_usage()

    assert calls["n"] == 2
    assert client.usage_log == [
        UsageRecord(
            model="test/model", cost_usd=0.0042, prompt_tokens=100, completion_tokens=50
        )
    ]


def test_resolve_records_zero_cost_when_fields_are_none():
    def get_generation(id):
        return SimpleNamespace(
            data=SimpleNamespace(
                total_cost=None, tokens_prompt=None, tokens_completion=None
            )
        )

    client = _client_with_fake_sdk(
        chat_send=lambda **_kw: _chat_response(),
        get_generation=get_generation,
    )

    client.complete(system="sys", user="usr")
    client.resolve_pending_usage()

    assert client.usage_log == [
        UsageRecord(model="test/model", cost_usd=0.0, prompt_tokens=0, completion_tokens=0)
    ]
