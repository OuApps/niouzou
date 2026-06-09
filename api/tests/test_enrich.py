"""Tests for the enrichment service and cron (E5-S1/S2).

No real OpenRouter and no real network: newspaper4k is monkeypatched and the
LLM client is a scripted fake. The cron tests are DB-backed and skip cleanly
when Postgres is unreachable (via the shared ``db_session`` fixture).
"""

import sys

import pytest
from sqlalchemy import func, select

from niouzou.models import ArticleKeyword, ArticleRelevanceScore
from niouzou.models.article import STATUS_ENRICHED, STATUS_PENDING
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.scoring.ai_keyword import AIKeywordScorer
from niouzou.services.enrichment_service import (
    EnrichmentService,
    _detect_language,
    _parse_enrichment,
)
from niouzou.services.scoring_service import ScoringService
from tests.factories import make_article, make_source, make_user
from tests.test_ai_keyword import FakeClient

_ARTICLE_TEXT = (
    "Rust is winning over systems programmers. Memory safety without a garbage "
    "collector is the headline feature. Adoption keeps climbing across industry. "
    "This fourth sentence should be dropped from the short summary."
)


class _FakeNewspaperArticle:
    """Stand-in for newspaper.Article controlled by class-level knobs."""

    text = _ARTICLE_TEXT
    top_image = "https://img.example/cover.jpg"
    raise_on_download = False

    def __init__(self, url, *args, **kwargs):
        self.url = url

    def download(self):
        if type(self).raise_on_download:
            raise RuntimeError("403 Forbidden")

    def parse(self):
        pass


@pytest.fixture
def fake_newspaper(monkeypatch):
    """Install a fresh fake ``newspaper`` module with resettable knobs."""
    import types

    module = types.ModuleType("newspaper")
    module.Article = _FakeNewspaperArticle
    _FakeNewspaperArticle.text = _ARTICLE_TEXT
    _FakeNewspaperArticle.top_image = "https://img.example/cover.jpg"
    _FakeNewspaperArticle.raise_on_download = False
    monkeypatch.setitem(sys.modules, "newspaper", module)
    return _FakeNewspaperArticle


# ── EnrichmentService.extract_content ────────────────────────────────────────


def test_extract_content_uses_newspaper(fake_newspaper):
    svc = EnrichmentService(openrouter_client=None)
    result = svc.extract_content("https://x/a", rss_fallback="<p>rss body</p>")
    assert result.content == _ARTICLE_TEXT
    assert result.og_image_url == "https://img.example/cover.jpg"


def test_extract_content_falls_back_to_rss_on_fetch_failure(fake_newspaper):
    fake_newspaper.raise_on_download = True
    svc = EnrichmentService(openrouter_client=None)
    result = svc.extract_content("https://x/a", rss_fallback="<p>RSS <b>body</b> here</p>")
    assert result.content == "RSS body here"  # HTML stripped
    assert result.og_image_url is None


def test_extract_content_falls_back_when_newspaper_text_empty(fake_newspaper):
    fake_newspaper.text = ""
    svc = EnrichmentService(openrouter_client=None)
    result = svc.extract_content("https://x/a", rss_fallback="plain rss")
    assert result.content == "plain rss"


# ── EnrichmentService.generate_enrichment ────────────────────────────────────


def test_generate_enrichment_without_ai_returns_empty_fallback():
    svc = EnrichmentService(openrouter_client=None)
    result = svc.generate_enrichment("Title", _ARTICLE_TEXT)
    assert result.summary_executive is None
    assert result.summary_short is None
    # Signals "AI not run" so the cron knows to fall back to TF-IDF.
    assert result.keywords is None


def test_generate_enrichment_with_ai_parses_json():
    client = FakeClient(
        [
            '{"summary_executive": "- a\\n- b", '
            '"keywords": [{"term": "rust", "salience": 0.9}]}'
        ]
    )
    svc = EnrichmentService(openrouter_client=client)
    result = svc.generate_enrichment("Title", _ARTICLE_TEXT)
    assert result.summary_short is None
    assert result.summary_executive == "- a\n- b"
    assert result.keywords is not None
    assert [kw.term for kw in result.keywords] == ["rust"]
    assert result.keywords[0].salience == 0.9


def test_generate_enrichment_degrades_to_fallback_on_llm_failure():
    client = FakeClient(["garbage", "still garbage"])  # never valid JSON
    svc = EnrichmentService(openrouter_client=client)
    result = svc.generate_enrichment("Title", _ARTICLE_TEXT)
    # Never raises — falls back to an empty Enrichment with keywords=None so
    # the cron triggers its TF-IDF fallback path.
    assert result.summary_short is None
    assert result.summary_executive is None
    assert result.keywords is None


def test_generate_enrichment_drops_malformed_keywords():
    client = FakeClient(
        [
            '{"summary_executive": "- bullet", '
            '"keywords": [{"term": "rust", "salience": 0.8}, '
            '{"term": "", "salience": 0.5}, '
            '{"term": "the", "salience": 0.5}, '
            '{"term": "rust", "salience": 0.3}, '
            '{"term": "memory safety", "salience": 1.5}]}'
        ]
    )
    svc = EnrichmentService(openrouter_client=client)
    result = svc.generate_enrichment("Title", _ARTICLE_TEXT)
    assert result.keywords is not None
    terms = [kw.term for kw in result.keywords]
    # Empty term, stopword "the", and duplicate "rust" all dropped. Salience
    # 1.5 is clamped to 1.0.
    assert terms == ["rust", "memory safety"]
    assert result.keywords[1].salience == 1.0


def test_ai_enabled_flag():
    assert EnrichmentService(openrouter_client=None).ai_enabled is False
    assert EnrichmentService(openrouter_client=FakeClient(["x"])).ai_enabled is True


# ── _parse_enrichment.summary_executive (E10-S2) ─────────────────────────────


def test_parse_executive_string_passthrough():
    result = _parse_enrichment({"summary_executive": "- a\n- b"})
    assert result.summary_executive == "- a\n- b"


def test_parse_executive_list_joined_as_bullets():
    """LLM sometimes returns an array — flattened into newline bullets."""
    result = _parse_enrichment(
        {"summary_executive": ["First point", "Second point"]}
    )
    assert result.summary_executive == "- First point\n- Second point"


def test_parse_executive_list_strips_existing_bullets():
    result = _parse_enrichment(
        {"summary_executive": ["- already bulleted", "* also bulleted"]}
    )
    assert result.summary_executive == "- already bulleted\n- also bulleted"


def test_parse_executive_empty_list_raises():
    """Empty summary_executive is treated as a failed enrichment so the cron
    retries / falls back, rather than persisting an article with no AI summary
    at all."""
    with pytest.raises(ValueError, match="summary_executive"):
        _parse_enrichment({"summary_executive": []})


def test_parse_executive_missing_raises():
    with pytest.raises(ValueError, match="summary_executive"):
        _parse_enrichment({"keywords": []})


# ── Language detection (E10-S2) ──────────────────────────────────────────────


def test_detect_language_french():
    assert _detect_language(
        "Le match du championnat",
        "Le club a remporté la victoire et le titre dans une finale qui s'est jouée hier soir.",
    ) == "fr"


def test_detect_language_english():
    assert _detect_language(
        "The new product release",
        "The company announced that a new product would ship by the end of the quarter.",
    ) == "en"


def test_detect_language_empty_returns_none():
    assert _detect_language("", "") is None
    assert _detect_language("1234 5678", "9 10 11") is None


def test_detect_language_ambiguous_returns_none():
    # Carefully balanced: same number of fr and en stop words. The detector
    # should refuse to guess rather than flip a coin.
    assert _detect_language("the le", "the le and et") is None


def test_generate_enrichment_includes_language_header():
    """When detected, ``Language: fr`` is prepended to the user prompt."""

    class _RecordingClient(FakeClient):
        def __init__(self, replies):
            super().__init__(replies)
            self.last_user: str | None = None

        def complete(self, *, system, user, temperature=0.2):
            self.last_user = user
            return super().complete(system=system, user=user, temperature=temperature)

    client = _RecordingClient(
        ['{"summary_executive": "- court", "keywords": []}']
    )
    svc = EnrichmentService(openrouter_client=client)
    svc.generate_enrichment(
        "Le club et le championnat",
        "Le club a remporté la victoire et le titre dans une finale qui s'est jouée hier soir.",
    )
    assert client.last_user is not None
    assert client.last_user.startswith("Language: fr\nTitle:")


def test_generate_enrichment_injects_vocab():
    """When set_vocab supplies terms, they appear in the user prompt."""

    class _RecordingClient(FakeClient):
        def __init__(self, replies):
            super().__init__(replies)
            self.last_user: str | None = None

        def complete(self, *, system, user, temperature=0.2):
            self.last_user = user
            return super().complete(system=system, user=user, temperature=temperature)

    client = _RecordingClient(
        ['{"summary_executive": "- x", "keywords": []}']
    )
    svc = EnrichmentService(openrouter_client=client)
    svc.set_vocab(["football", "fc barcelone", "ligue des champions"])
    svc.generate_enrichment("Title", "Some content body here.")
    assert client.last_user is not None
    assert (
        "Existing vocabulary (reuse when applicable): football, fc barcelone, ligue des champions"
        in client.last_user
    )


def test_generate_enrichment_huge_vocab_preserves_article():
    """Regression: a vocab dump larger than the prompt budget must not
    starve out the article body. Before the fix the naive slice kept the
    vocab and dropped Title+content entirely, so the LLM replied
    "Please provide the news article" and every enrichment fell back to
    TF-IDF in production."""

    class _RecordingClient(FakeClient):
        def __init__(self, replies):
            super().__init__(replies)
            self.last_user: str | None = None

        def complete(self, *, system, user, temperature=0.2):
            self.last_user = user
            return super().complete(system=system, user=user, temperature=temperature)

    client = _RecordingClient(
        ['{"summary_executive": "- x", "keywords": []}']
    )
    svc = EnrichmentService(openrouter_client=client)
    # 200 terms ~12 chars each → far past the prompt budget.
    svc.set_vocab([f"longish-keyword-term-{i:03d}" for i in range(200)])
    svc.generate_enrichment("UniqueTitle", "ArticleBodyMarker " * 50)
    assert client.last_user is not None
    assert "UniqueTitle" in client.last_user
    assert "ArticleBodyMarker" in client.last_user


def test_parse_executive_nested_list_drops_inner_lists():
    result = _parse_enrichment(
        {"summary_executive": ["valid", ["nested", "stuff"], "also valid"]}
    )
    assert result.summary_executive == "- valid\n- also valid"


# ── cron enrich_article (DB-backed) ──────────────────────────────────────────


async def _pending_article(db_session, *, content="<p>rss</p>"):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, status=STATUS_PENDING)
    article.content = content
    await db_session.flush()
    return user, article


async def test_enrich_article_full_ai_path(fake_newspaper, db_session):
    from niouzou.crons.enrich import enrich_article

    user, article = await _pending_article(db_session)
    # One combined LLM reply now carries summaries + keywords.
    enrichment = EnrichmentService(
        FakeClient(
            [
                '{"summary_executive": "- bullet", '
                '"keywords": [{"term": "rust", "salience": 0.9}]}'
            ]
        )
    )
    # AI pipeline is still needed for the relevance-score path and the
    # ``scorer`` indicator stored on article_relevance_scores. Its scorer's
    # ``extract_keywords`` is no longer called from the cron — the AI keywords
    # come from the EnrichmentService reply.
    ai_scoring = ScoringService(ScoringPipeline(AIKeywordScorer(FakeClient([]))))
    tfidf_scoring = ScoringService(ScoringPipeline(TFIDFScorer()))

    await enrich_article(
        db_session,
        article,
        enrichment=enrichment,
        ai_scoring=ai_scoring,
        tfidf_scoring=tfidf_scoring,
    )

    assert article.status == STATUS_ENRICHED
    assert article.enriched_at is not None
    assert article.content == _ARTICLE_TEXT
    assert article.summary_short is None  # no longer generated
    assert article.summary_executive == "- bullet"
    # E7-S15: successful AI path records the method, no error.
    assert article.enrichment_method == "ai"
    assert article.enrichment_error is None

    terms = (
        await db_session.execute(
            select(ArticleKeyword.term).where(ArticleKeyword.article_id == article.id)
        )
    ).scalars().all()
    assert terms == ["rust"]

    score = await db_session.scalar(
        select(ArticleRelevanceScore.relevance_score).where(
            ArticleRelevanceScore.article_id == article.id,
            ArticleRelevanceScore.user_id == user.id,
        )
    )
    assert score is not None and 0.0 <= score <= 1.0


async def test_enrich_article_falls_back_to_tfidf_on_ai_keyword_failure(
    fake_newspaper, db_session
):
    from niouzou.crons.enrich import enrich_article

    user, article = await _pending_article(db_session)
    # LLM enrichment call always fails → cron must fall back to TF-IDF for
    # both summaries (newspaper first sentences) and keywords.
    enrichment = EnrichmentService(FakeClient(["nope", "nope"]))
    ai_scoring = ScoringService(ScoringPipeline(AIKeywordScorer(FakeClient([]))))
    tfidf_scoring = ScoringService(ScoringPipeline(TFIDFScorer()))

    await enrich_article(
        db_session,
        article,
        enrichment=enrichment,
        ai_scoring=ai_scoring,
        tfidf_scoring=tfidf_scoring,
    )

    assert article.status == STATUS_ENRICHED
    keyword_count = await db_session.scalar(
        select(func.count())
        .select_from(ArticleKeyword)
        .where(ArticleKeyword.article_id == article.id)
    )
    assert keyword_count > 0  # TF-IDF produced keywords from the article text
    # E7-S15: fallback path records 'tfidf' + the captured AI error string.
    assert article.enrichment_method == "tfidf"
    assert article.enrichment_error  # non-empty string from the AI failure


async def test_run_closes_openrouter_client(monkeypatch):
    """run() must close the shared OpenRouter client even on an empty batch."""
    import contextlib

    import niouzou.crons.enrich as enrich_mod
    from niouzou.services.settings_service import EffectiveConfig

    class _ClosableClient:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    client = _ClosableClient()
    monkeypatch.setattr(
        enrich_mod.OpenRouterClient,
        "from_overrides",
        classmethod(lambda cls, api_key, model: client),
    )

    @contextlib.asynccontextmanager
    async def _fake_scope():
        yield None

    async def _no_pending(session, limit):
        return []

    async def _fake_get_effective(self):
        return EffectiveConfig(
            openrouter_api_key="sk-test",
            openrouter_model="test/model",
            max_keywords_per_article=6,
            cron_fetch_interval=15,
            cron_refresh_weights_hour=3,
            score_threshold=0.0,
        )

    monkeypatch.setattr(
        enrich_mod.SettingsService, "get_effective", _fake_get_effective
    )
    monkeypatch.setattr(enrich_mod, "session_scope", _fake_scope)
    monkeypatch.setattr(enrich_mod, "_pending_article_ids", _no_pending)

    async def _no_vocab(session, limit):
        return []

    async def _no_prompts(session):
        return {}

    monkeypatch.setattr(enrich_mod, "_load_top_keywords", _no_vocab)
    monkeypatch.setattr(enrich_mod, "load_all_into_dict", _no_prompts)

    assert await enrich_mod.run() == 0
    assert client.closed is True


async def test_enrich_article_no_ai_path(fake_newspaper, db_session):
    from niouzou.crons.enrich import enrich_article

    user, article = await _pending_article(db_session)
    tfidf_scoring = ScoringService(ScoringPipeline(TFIDFScorer()))

    await enrich_article(
        db_session,
        article,
        enrichment=EnrichmentService(openrouter_client=None),
        ai_scoring=tfidf_scoring,
        tfidf_scoring=tfidf_scoring,
    )

    assert article.status == STATUS_ENRICHED
    assert article.summary_executive is None  # no AI → no executive summary
    assert article.summary_short is None  # no longer generated, even off-AI
    # E7-S15: pure TF-IDF (AI off) records the method without an error.
    assert article.enrichment_method == "tfidf"
    assert article.enrichment_error is None
