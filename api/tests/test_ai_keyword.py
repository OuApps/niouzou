"""Unit tests for AIKeywordScorer (E5-S3) — no real OpenRouter, no DB.

A FakeClient subclasses OpenRouterClient and overrides only ``complete`` (the
HTTP layer), so the real JSON-extraction, retry and parse logic is exercised
without any network call.
"""

import pytest

from niouzou.scoring import ScoringPipeline
from niouzou.scoring.ai_keyword import AIKeywordScorer
from niouzou.services.openrouter_client import OpenRouterClient, OpenRouterError


class FakeClient(OpenRouterClient):
    """OpenRouterClient with a scripted ``complete`` and no httpx/network."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = 0

    def complete(self, *, system, user, temperature=0.2):
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        if isinstance(reply, Exception):
            raise reply
        return reply


def _scorer(replies, **kw):
    return AIKeywordScorer(FakeClient(replies), **kw)


def test_parses_keywords_object_form():
    scorer = _scorer(
        ['{"keywords": [{"term": "Rust", "salience": 0.9}, {"term": "safety", "salience": 0.5}]}']
    )
    kws = scorer.extract_keywords("some article text")
    assert [(k.term, k.salience) for k in kws] == [("rust", 0.9), ("safety", 0.5)]


def test_parses_bare_list_with_prose_and_fence():
    scorer = _scorer(
        ['Here you go:\n```json\n[{"term": "AI", "salience": 1.0}]\n```\nHope it helps!']
    )
    kws = scorer.extract_keywords("text")
    assert [(k.term, k.salience) for k in kws] == [("ai", 1.0)]


def test_salience_clamped_into_unit_range():
    scorer = _scorer(
        ['[{"term": "a", "salience": 1.7}, {"term": "b", "salience": -0.4}]']
    )
    kws = {k.term: k.salience for k in scorer.extract_keywords("text")}
    assert kws == {"a": 1.0, "b": 0.0}
    assert all(0.0 <= s <= 1.0 for s in kws.values())


def test_duplicates_removed_keeping_first():
    scorer = _scorer(
        ['[{"term": "Rust", "salience": 0.9}, {"term": "rust", "salience": 0.2}]']
    )
    kws = scorer.extract_keywords("text")
    assert [(k.term, k.salience) for k in kws] == [("rust", 0.9)]


def test_max_keywords_enforced():
    items = ",".join(f'{{"term": "t{i}", "salience": 0.5}}' for i in range(20))
    scorer = _scorer([f"[{items}]"], max_keywords=5)
    assert len(scorer.extract_keywords("text")) == 5


def test_empty_text_returns_no_keywords_without_calling_llm():
    client = FakeClient(['[{"term": "x", "salience": 1}]'])
    scorer = AIKeywordScorer(client)
    assert scorer.extract_keywords("   ") == []
    assert client.calls == 0


def test_malformed_then_valid_is_retried_once():
    scorer = _scorer(["not json at all", '[{"term": "ok", "salience": 0.8}]'])
    kws = scorer.extract_keywords("text")
    assert [k.term for k in kws] == ["ok"]
    assert scorer._client.calls == 2  # one failure, one success


def test_persistently_malformed_raises_after_retry():
    scorer = _scorer(["nope", "still nope", "and again"])
    with pytest.raises(OpenRouterError):
        scorer.extract_keywords("text")
    assert scorer._client.calls == 2  # retries=1 → exactly two attempts


def test_empty_keyword_list_is_rejected():
    # A well-formed reply that yields nothing usable should fail (→ TF-IDF).
    scorer = _scorer(['{"keywords": []}', '{"keywords": []}'])
    with pytest.raises(OpenRouterError):
        scorer.extract_keywords("text")


def test_missing_api_key_raises_when_no_client_injected(monkeypatch):
    import niouzou.services.openrouter_client as mod

    monkeypatch.setattr(mod.OpenRouterClient, "from_settings", classmethod(lambda cls: None))
    with pytest.raises(OpenRouterError):
        AIKeywordScorer().extract_keywords("text")


def test_pipeline_relevance_stays_in_unit_range_with_ai_scorer():
    scorer = _scorer(['[{"term": "rust", "salience": 1.0}]'])
    pipeline = ScoringPipeline(scorer)
    kws = pipeline.extract_keywords("rust article")
    for weight in (-1000.0, -1.0, 0.0, 1.0, 1000.0):
        assert 0.0 <= pipeline.relevance(kws, {"rust": weight}) <= 1.0
