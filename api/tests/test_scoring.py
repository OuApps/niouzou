"""Unit tests for the scoring pipeline (E3-S4) — no database required.

Covers the four cases mandated by docs/CONVENTIONS.md: neutral user, positive
keywords, negative keywords, and mixed.
"""

import pytest

from niouzou.scoring import ScoredKeyword, ScoringPipeline, TFIDFScorer
from niouzou.scoring.pipeline import ScoringPipeline as Pipeline

ARTICLE = (
    "Rust memory safety makes Rust great for systems programming. "
    "Rust beats C++ on safety. Rust Rust safety safety."
)


@pytest.fixture
def pipeline() -> ScoringPipeline:
    return ScoringPipeline(TFIDFScorer())


def _keywords(pipeline: ScoringPipeline) -> list[ScoredKeyword]:
    return pipeline.extract_keywords(ARTICLE)


def test_extraction_ranks_most_frequent_term_highest(pipeline):
    kws = _keywords(pipeline)
    assert kws[0].term == "rust"
    assert kws[0].salience == 1.0
    # Stopwords ("for", "on", ...) are filtered out.
    terms = {k.term for k in kws}
    assert "for" not in terms and "on" not in terms
    # All saliences within [0, 1].
    assert all(0.0 <= k.salience <= 1.0 for k in kws)


def test_neutral_user_scores_one_half(pipeline):
    # New user, no weights → raw contribution 0 → relevance 0.5 (passes the
    # default threshold of 0.0, so new users see everything).
    assert pipeline.relevance(_keywords(pipeline), {}) == 0.5


def test_positive_keywords_raise_score(pipeline):
    score = pipeline.relevance(_keywords(pipeline), {"rust": 2.0})
    assert score > 0.5


def test_negative_keywords_lower_score(pipeline):
    score = pipeline.relevance(_keywords(pipeline), {"rust": -2.0})
    assert score < 0.5


def test_mixed_weights_between_extremes(pipeline):
    pos = pipeline.relevance(_keywords(pipeline), {"rust": 2.0})
    neg = pipeline.relevance(_keywords(pipeline), {"rust": -2.0})
    mixed = pipeline.relevance(_keywords(pipeline), {"rust": 2.0, "safety": -1.0})
    assert neg < mixed < pos


def test_unknown_keywords_are_neutral(pipeline):
    # A weight on a term the article doesn't contain has no effect.
    assert pipeline.relevance(_keywords(pipeline), {"php": 5.0}) == 0.5


def test_relevance_always_within_unit_range(pipeline):
    kws = _keywords(pipeline)
    for weight in (-1000.0, -1.0, 0.0, 1.0, 1000.0):
        score = pipeline.relevance(kws, {"rust": weight})
        assert 0.0 <= score <= 1.0


def test_empty_text_yields_no_keywords(pipeline):
    assert pipeline.extract_keywords("") == []


def test_idf_downweights_terms_common_across_corpus():
    scorer = TFIDFScorer()
    corpus = ["rust rust rust", "rust safety", "rust performance"]
    # "rust" appears in every doc → low IDF; the rarer term should outrank it.
    kws = scorer.extract_keywords("rust safety safety", corpus=corpus)
    salience = {k.term: k.salience for k in kws}
    assert salience["safety"] > salience["rust"]


def test_pipeline_selects_tfidf_without_api_key(monkeypatch):
    from niouzou import config

    config.get_settings.cache_clear()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert isinstance(Pipeline()._select_scorer(), TFIDFScorer)
    config.get_settings.cache_clear()
