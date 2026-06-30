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
from niouzou.services.embedding_service import EmbeddingService
from niouzou.services.enrichment_service import (
    EnrichmentService,
    _detect_language,
    _parse_boilerplate_exact,
    _parse_boilerplate_markers,
    _parse_enrichment,
    _text_is_boilerplate,
)
from niouzou.services.scoring_service import ScoringService
from tests.factories import make_article, make_source, make_user
from tests.fake_embeddings import HashEncoder
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


def test_extract_content_falls_back_on_boilerplate(fake_newspaper):
    """E10-S6 — newspaper returns a paywall footer → RSS teaser used instead."""
    fake_newspaper.text = _EBRA_BOILERPLATE
    svc = EnrichmentService(openrouter_client=None)
    result = svc.extract_content(
        "https://x/a", rss_fallback="<p>Le vrai extrait gratuit de l'article.</p>"
    )
    assert result.content == "Le vrai extrait gratuit de l'article."


def test_extract_content_keeps_short_non_boilerplate(fake_newspaper):
    """A genuine short extraction is kept — no spurious fallback."""
    fake_newspaper.text = "Un court article tout à fait légitime sur l'actualité locale."
    svc = EnrichmentService(openrouter_client=None)
    result = svc.extract_content("https://x/a", rss_fallback="<p>ignored</p>")
    assert result.content == "Un court article tout à fait légitime sur l'actualité locale."


# ── Boilerplate detection (E10-S6) ───────────────────────────────────────────

# Realistic EBRA RGPD footer fragment — what newspaper4k scrapes on paywalled
# « Le Progrès » articles. The source-specific marker ``dpo@ebra.fr`` is what
# the built-in detector keys on.
_EBRA_BOILERPLATE = (
    "Le Progrès, en tant que responsable de traitement, met en œuvre des "
    "traitements de données à caractère personnel pour la "
    "fourniture de ses produits et services. Pour toute question relative à "
    "vos données, vous pouvez contacter notre Délégué à "
    "la Protection des Données personnelles (dpo@ebra.fr)."
)

# A genuine article *about* the RGPD/CNIL/cookies — contains the topic
# vocabulary but none of the CMS/EBRA source-specific markers.
_RGPD_ARTICLE = (
    "La CNIL a infligé une amende record à une entreprise pour "
    "non-respect du RGPD. Les données personnelles de millions "
    "d'utilisateurs étaient collectées via des cookies sans "
    "consentement valable, en violation de la protection des données."
)

_BUILTIN_MARKERS = (
    ("dpo@ebra.fr",),
    ("service relations clients", "abonnements et autres services souscrits"),
    ("lprventesweb@leprogres.fr",),
)


def test_is_boilerplate_detects_ebra_via_marker():
    svc = EnrichmentService(openrouter_client=None)
    assert svc._is_boilerplate(_EBRA_BOILERPLATE) is True


def test_is_boilerplate_no_false_positive_on_rgpd_article():
    """Anti thematic false-positive: an article on RGPD/CNIL/cookies is kept."""
    svc = EnrichmentService(openrouter_client=None)
    assert svc._is_boilerplate(_RGPD_ARTICLE) is False


def test_is_boilerplate_no_false_positive_on_short_real_extract():
    svc = EnrichmentService(openrouter_client=None)
    teaser = (
        "Un incendie s'est déclaré mardi soir dans un entrepôt "
        "de la zone industrielle. Les pompiers sont rapidement intervenus."
    )
    assert svc._is_boilerplate(teaser) is False


def test_is_boilerplate_exact_match_normalizes_whitespace():
    """Exact template matches even with \\xa0 / collapsed multiple spaces."""
    template = "By using this site you accept our cookies policy."
    exact = tuple(_parse_boilerplate_exact(template))
    noisy = "By using   this site\nyou accept our    cookies policy."
    assert _text_is_boilerplate(noisy, exact_templates=exact, marker_groups=()) is True
    assert (
        _text_is_boilerplate(
            "An unrelated sentence.", exact_templates=exact, marker_groups=()
        )
        is False
    )


def test_is_boilerplate_marker_group_requires_all_substrings():
    """A two-substring group only trips when BOTH co-occur."""
    groups = (("service relations clients", "abonnements et autres services souscrits"),)
    only_one = "Contactez notre Service Relations Clients pour toute demande."
    both = (
        "Service Relations Clients pour vos abonnements et autres services "
        "souscrits auprès du journal."
    )
    assert _text_is_boilerplate(only_one, exact_templates=(), marker_groups=groups) is False
    assert _text_is_boilerplate(both, exact_templates=(), marker_groups=groups) is True


def test_parse_boilerplate_markers_splits_groups_and_substrings():
    groups = _parse_boilerplate_markers("a&&b|||c|||  ")
    assert groups == [("a", "b"), ("c",)]


def test_parse_boilerplate_exact_normalizes_and_drops_empties():
    assert _parse_boilerplate_exact("Foo Bar|||   |||baz") == ["Foo Bar", "baz"]


# ── EnrichmentService.generate_enrichment ────────────────────────────────────


def test_generate_enrichment_without_ai_returns_empty_fallback():
    svc = EnrichmentService(openrouter_client=None)
    result = svc.generate_enrichment("Title", _ARTICLE_TEXT)
    assert result.summary_executive is None
    assert result.summary_short is None
    # Signals "AI not run" — the cron stores no keywords (keyword_score NULL).
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
    # the cron records the failure and stores no keywords.
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


def test_generate_enrichment_respects_max_input_chars():
    """The configurable cap bounds the combined LLM input: a body longer than
    ``max_input_chars`` is truncated, a higher cap lets more through."""

    class _RecordingClient(FakeClient):
        def __init__(self, replies):
            super().__init__(replies)
            self.last_user: str | None = None

        def complete(self, *, system, user, temperature=0.2):
            self.last_user = user
            return super().complete(system=system, user=user, temperature=temperature)

    long_body = "x" * 10000
    replies = ['{"summary_executive": "- x", "keywords": []}']

    tight = _RecordingClient(list(replies))
    svc_tight = EnrichmentService(openrouter_client=tight, max_input_chars=1000)
    svc_tight.generate_enrichment("Title", long_body)
    assert tight.last_user is not None
    assert len(tight.last_user) <= 1000

    wide = _RecordingClient(list(replies))
    svc_wide = EnrichmentService(openrouter_client=wide, max_input_chars=8000)
    svc_wide.generate_enrichment("Title", long_body)
    assert wide.last_user is not None
    assert len(wide.last_user) > 1000
    assert len(wide.last_user) <= 8000


def test_generate_enrichment_combines_rss_teaser_and_body():
    """A distinct RSS teaser is sent alongside the fetched body, both labeled."""

    class _RecordingClient(FakeClient):
        def __init__(self, replies):
            super().__init__(replies)
            self.last_user: str | None = None

        def complete(self, *, system, user, temperature=0.2):
            self.last_user = user
            return super().complete(system=system, user=user, temperature=temperature)

    client = _RecordingClient(['{"summary_executive": "- x", "keywords": []}'])
    svc = EnrichmentService(openrouter_client=client)
    svc.generate_enrichment(
        "Title",
        "Full fetched article body with all the details.",
        rss_teaser="<p>Publisher teaser blurb.</p>",
    )
    assert client.last_user is not None
    assert "RSS summary: Publisher teaser blurb." in client.last_user
    assert "Article body: Full fetched article body" in client.last_user


def test_generate_enrichment_dedupes_rss_teaser_contained_in_body():
    """When the teaser is already inside the body, the teaser block is dropped."""

    class _RecordingClient(FakeClient):
        def __init__(self, replies):
            super().__init__(replies)
            self.last_user: str | None = None

        def complete(self, *, system, user, temperature=0.2):
            self.last_user = user
            return super().complete(system=system, user=user, temperature=temperature)

    client = _RecordingClient(['{"summary_executive": "- x", "keywords": []}'])
    svc = EnrichmentService(openrouter_client=client)
    body = "Publisher teaser blurb. And then much more detail follows here."
    svc.generate_enrichment(
        "Title", body, rss_teaser="<p>Publisher teaser blurb.</p>"
    )
    assert client.last_user is not None
    # No duplicated teaser block; the body (which contains it) is sent as-is.
    assert "RSS summary:" not in client.last_user
    assert "Publisher teaser blurb." in client.last_user


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


def _scoring() -> ScoringService:
    # E16-S8 — a single ScoringService computes both scores; the pipeline is
    # only used for the pure relevance maths, never for extraction.
    return ScoringService(ScoringPipeline(TFIDFScorer()))


def _fake_embedder() -> EmbeddingService:
    return EmbeddingService(HashEncoder())


async def _dual_scores(db_session, article, user):
    return (
        await db_session.execute(
            select(
                ArticleRelevanceScore.keyword_score,
                ArticleRelevanceScore.smart_score,
            ).where(
                ArticleRelevanceScore.article_id == article.id,
                ArticleRelevanceScore.user_id == user.id,
            )
        )
    ).first()


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

    await enrich_article(
        db_session,
        article,
        enrichment=enrichment,
        scoring=_scoring(),
        embedder=_fake_embedder(),
    )

    assert article.status == STATUS_ENRICHED
    assert article.enriched_at is not None
    assert article.content == _ARTICLE_TEXT
    assert article.summary_short is None  # no longer generated
    assert article.summary_executive == "- bullet"
    # E7-S15: successful AI path records the method, no error.
    assert article.enrichment_method == "ai"
    assert article.enrichment_error is None
    assert article.embedding is not None

    terms = (
        await db_session.execute(
            select(ArticleKeyword.term).where(ArticleKeyword.article_id == article.id)
        )
    ).scalars().all()
    assert terms == ["rust"]

    # E16-S8: LLM on + embedder on → BOTH scores populated.
    scores = await _dual_scores(db_session, article, user)
    assert scores is not None
    assert scores.keyword_score is not None and 0.0 <= scores.keyword_score <= 1.0
    assert scores.smart_score is not None and 0.0 <= scores.smart_score <= 1.0


async def test_enrich_article_llm_failure_keeps_smart_score(
    fake_newspaper, db_session
):
    """LLM down → no keywords (keyword_score NULL), but the local embedding
    still yields a smart_score and the article surfaces (E16-S8 — the TF-IDF
    fallback is gone)."""
    from niouzou.crons.enrich import enrich_article

    user, article = await _pending_article(db_session)
    # LLM enrichment call always fails → keyword extraction is LLM-only now,
    # so no keywords are stored at all.
    enrichment = EnrichmentService(FakeClient(["nope", "nope"]))

    await enrich_article(
        db_session,
        article,
        enrichment=enrichment,
        scoring=_scoring(),
        embedder=_fake_embedder(),
    )

    assert article.status == STATUS_ENRICHED
    keyword_count = await db_session.scalar(
        select(func.count())
        .select_from(ArticleKeyword)
        .where(ArticleKeyword.article_id == article.id)
    )
    assert keyword_count == 0
    assert article.enrichment_method is None
    assert article.enrichment_error  # non-empty string from the AI failure

    scores = await _dual_scores(db_session, article, user)
    assert scores.keyword_score is None
    assert scores.smart_score is not None


async def test_enrich_article_embedder_off_keyword_only(
    fake_newspaper, db_session
):
    """No embedder installed → smart_score NULL, keyword_score populated."""
    from niouzou.crons.enrich import enrich_article

    user, article = await _pending_article(db_session)
    enrichment = EnrichmentService(
        FakeClient(
            [
                '{"summary_executive": "- bullet", '
                '"keywords": [{"term": "rust", "salience": 0.9}]}'
            ]
        )
    )

    await enrich_article(
        db_session,
        article,
        enrichment=enrichment,
        scoring=_scoring(),
        embedder=None,
    )

    assert article.status == STATUS_ENRICHED
    assert article.embedding is None
    scores = await _dual_scores(db_session, article, user)
    assert scores.keyword_score is not None
    assert scores.smart_score is None


async def test_enrich_never_reaches_tfidf_extractor(
    fake_newspaper, db_session, monkeypatch
):
    """E16-S8 acceptance — no code path from cron_enrich extracts TF-IDF
    keywords anymore, even when the LLM fails."""
    from niouzou.crons.enrich import enrich_article

    def _tripwire(self, text, *, corpus=None):
        raise AssertionError("TFIDFScorer.extract_keywords reached from cron_enrich")

    monkeypatch.setattr(TFIDFScorer, "extract_keywords", _tripwire)

    user, article = await _pending_article(db_session)
    await enrich_article(
        db_session,
        article,
        enrichment=EnrichmentService(FakeClient(["nope", "nope"])),
        scoring=_scoring(),
        embedder=_fake_embedder(),
    )
    assert article.status == STATUS_ENRICHED


async def test_run_closes_openrouter_client(monkeypatch):
    """run() must close the shared OpenRouter client even on an empty batch."""
    import contextlib

    import niouzou.crons.enrich as enrich_mod
    from niouzou.services.settings_service import EffectiveConfig

    class _ClosableClient:
        def __init__(self):
            self.closed = False
            self.usage_log = []

        def resolve_pending_usage(self):
            pass

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
            cron_nightly_refresh_hour=3,
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


async def test_enrich_article_no_ai_no_embedder(fake_newspaper, db_session):
    """Both inputs off → both scores NULL, article still enriched and
    surfaces (badge «–»/«–», E16-S8)."""
    from niouzou.crons.enrich import enrich_article

    user, article = await _pending_article(db_session)

    await enrich_article(
        db_session,
        article,
        enrichment=EnrichmentService(openrouter_client=None),
        scoring=_scoring(),
        embedder=None,
    )

    assert article.status == STATUS_ENRICHED
    assert article.summary_executive is None  # no AI → no executive summary
    assert article.summary_short is None  # no longer generated, even off-AI
    # AI off is not an error — method stays NULL, no error recorded.
    assert article.enrichment_method is None
    assert article.enrichment_error is None

    scores = await _dual_scores(db_session, article, user)
    assert scores.keyword_score is None
    assert scores.smart_score is None
