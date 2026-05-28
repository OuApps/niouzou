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
from niouzou.services.enrichment_service import EnrichmentService, _first_sentences
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
    assert result.fallback_summary.endswith("across industry.")


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


# ── EnrichmentService.generate_summaries ─────────────────────────────────────


def test_generate_summaries_without_ai_uses_first_sentences():
    svc = EnrichmentService(openrouter_client=None)
    summaries = svc.generate_summaries("Title", _ARTICLE_TEXT)
    assert summaries.summary_executive is None
    assert summaries.summary_short == _first_sentences(_ARTICLE_TEXT)


def test_generate_summaries_with_ai_parses_json():
    client = FakeClient(
        ['{"summary_short": "Punchy three liner.", "summary_executive": "- a\\n- b"}']
    )
    svc = EnrichmentService(openrouter_client=client)
    summaries = svc.generate_summaries("Title", _ARTICLE_TEXT)
    assert summaries.summary_short == "Punchy three liner."
    assert summaries.summary_executive == "- a\n- b"


def test_generate_summaries_degrades_to_fallback_on_llm_failure():
    client = FakeClient(["garbage", "still garbage"])  # never valid JSON
    svc = EnrichmentService(openrouter_client=client)
    summaries = svc.generate_summaries("Title", _ARTICLE_TEXT)
    # Never raises — falls back to first sentences.
    assert summaries.summary_short == _first_sentences(_ARTICLE_TEXT)
    assert summaries.summary_executive is None


def test_ai_enabled_flag():
    assert EnrichmentService(openrouter_client=None).ai_enabled is False
    assert EnrichmentService(openrouter_client=FakeClient(["x"])).ai_enabled is True


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
    enrichment = EnrichmentService(
        FakeClient(['{"summary_short": "Short.", "summary_executive": "- bullet"}'])
    )
    ai_scoring = ScoringService(
        ScoringPipeline(AIKeywordScorer(FakeClient(['[{"term": "rust", "salience": 0.9}]'])))
    )
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
    assert article.summary_short == "Short."
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
    enrichment = EnrichmentService(openrouter_client=None)  # no AI summaries
    # AI keyword scorer that always fails → cron must fall back to TF-IDF.
    ai_scoring = ScoringService(
        ScoringPipeline(AIKeywordScorer(FakeClient(["nope", "nope"])))
    )
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

    class _ClosableClient:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    client = _ClosableClient()
    monkeypatch.setattr(
        enrich_mod.OpenRouterClient, "from_settings", classmethod(lambda cls: client)
    )

    @contextlib.asynccontextmanager
    async def _fake_scope():
        yield None

    async def _no_pending(session, limit):
        return []

    monkeypatch.setattr(enrich_mod, "session_scope", _fake_scope)
    monkeypatch.setattr(enrich_mod, "_pending_article_ids", _no_pending)

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
    assert article.summary_short  # newspaper-derived
    # E7-S15: pure TF-IDF (AI off) records the method without an error.
    assert article.enrichment_method == "tfidf"
    assert article.enrichment_error is None
