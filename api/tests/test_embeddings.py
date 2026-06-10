"""E16-S2 — embedding service, cron_enrich integration, backfill CLI.

The real model is never loaded here (absolute rule, Notes E16): every test
injects a fake encoder from ``tests/fake_embeddings.py``. The DB-backed tests
skip cleanly when Postgres is unreachable (shared ``db_session`` fixture).
"""

import sys
import types

import numpy as np
import pytest

from niouzou.models.article import STATUS_ENRICHED, STATUS_PENDING
from niouzou.scoring import ScoringPipeline, TFIDFScorer
from niouzou.services import embedding_service
from niouzou.services.embedding_service import (
    EMBEDDING_DIM,
    EmbeddingService,
    build_article_text,
)
from niouzou.services.enrichment_service import EnrichmentService
from niouzou.services.scoring_service import ScoringService
from tests.factories import make_article, make_source, make_user
from tests.fake_embeddings import HashEncoder


# ── build_article_text ────────────────────────────────────────────────────────


def test_build_text_title_plus_summary():
    assert build_article_text("Title", "- b1\n- b2", "body") == "Title - b1\n- b2"


def test_build_text_falls_back_to_content_prefix():
    text = build_article_text("Title", None, "x" * 5000)
    assert text == "Title " + "x" * 1000


def test_build_text_empty_everything_embeds_title_alone():
    # Spec: empty text → no exception, embed the title alone.
    assert build_article_text("Title", None, None) == "Title"
    assert build_article_text("Title", "   ", "") == "Title"


# ── EmbeddingService ──────────────────────────────────────────────────────────


def test_embed_article_dimension_and_norm():
    vec = EmbeddingService(HashEncoder()).embed_article("Title", "summary", None)
    assert len(vec) == EMBEDDING_DIM
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-9


def test_embed_normalises_any_encoder_output():
    class RawEncoder:
        def encode(self, texts):
            return np.full((len(texts), EMBEDDING_DIM), 3.0)

    vec = EmbeddingService(RawEncoder()).embed_article("T", None, None)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-9


def test_wrong_encoder_dimension_raises():
    class WrongDim:
        def encode(self, texts):
            return np.ones((len(texts), 8))

    with pytest.raises(ValueError):
        EmbeddingService(WrongDim()).embed_article("T", None, None)


def test_loader_called_once_per_process(monkeypatch):
    calls = 0
    encoder = HashEncoder()

    def counting_loader():
        nonlocal calls
        calls += 1
        return encoder

    monkeypatch.setattr(embedding_service, "_load_encoder", counting_loader)
    svc = EmbeddingService()  # no injected encoder → goes through the loader
    svc.embed_article("a", None, None)
    svc.embed_article("b", None, None)
    assert calls == 1


def test_get_embedding_service_is_a_singleton():
    assert (
        embedding_service.get_embedding_service()
        is embedding_service.get_embedding_service()
    )


# ── cron_enrich integration (DB-backed) ───────────────────────────────────────


@pytest.fixture
def fake_newspaper(monkeypatch):
    class _FakeArticle:
        text = "Body text about something newsworthy happening today."
        top_image = None

        def __init__(self, url, *args, **kwargs):
            self.url = url

        def download(self):
            pass

        def parse(self):
            pass

    module = types.ModuleType("newspaper")
    module.Article = _FakeArticle
    monkeypatch.setitem(sys.modules, "newspaper", module)
    return _FakeArticle


async def _pending_article(db_session):
    user = await make_user(db_session)
    source = await make_source(db_session, user)
    article = await make_article(db_session, source, status=STATUS_PENDING)
    article.content = "<p>rss</p>"
    await db_session.flush()
    return article


async def test_enrich_article_stores_embedding(fake_newspaper, db_session):
    from niouzou.crons.enrich import enrich_article

    article = await _pending_article(db_session)
    tfidf = ScoringService(ScoringPipeline(TFIDFScorer()))

    await enrich_article(
        db_session,
        article,
        enrichment=EnrichmentService(None),  # AI off — embedding is unrelated
        ai_scoring=tfidf,
        tfidf_scoring=tfidf,
        embedder=EmbeddingService(HashEncoder()),
    )

    assert article.status == STATUS_ENRICHED
    emb = np.asarray(article.embedding, dtype=np.float64)
    assert emb.shape == (EMBEDDING_DIM,)
    assert abs(np.linalg.norm(emb) - 1.0) < 1e-6


async def test_enrich_article_without_embedder_leaves_null(
    fake_newspaper, db_session
):
    from niouzou.crons.enrich import enrich_article

    article = await _pending_article(db_session)
    tfidf = ScoringService(ScoringPipeline(TFIDFScorer()))

    await enrich_article(
        db_session,
        article,
        enrichment=EnrichmentService(None),
        ai_scoring=tfidf,
        tfidf_scoring=tfidf,
        embedder=None,  # sentence-transformers not installed
    )

    assert article.status == STATUS_ENRICHED
    assert article.embedding is None


async def test_embedding_failure_does_not_abort_enrichment(
    fake_newspaper, db_session
):
    from niouzou.crons.enrich import enrich_article

    class ExplodingEncoder:
        def encode(self, texts):
            raise RuntimeError("boom")

    article = await _pending_article(db_session)
    tfidf = ScoringService(ScoringPipeline(TFIDFScorer()))

    await enrich_article(
        db_session,
        article,
        enrichment=EnrichmentService(None),
        ai_scoring=tfidf,
        tfidf_scoring=tfidf,
        embedder=EmbeddingService(ExplodingEncoder()),
    )

    assert article.status == STATUS_ENRICHED  # enrichment survived
    assert article.embedding is None


# ── backfill CLI (DB-backed) ──────────────────────────────────────────────────


async def test_backfill_embeds_all_null_rows_then_noop(db_session):
    from niouzou.tools import backfill_embeddings

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    for i in range(3):
        await make_article(db_session, source, title=f"Article {i}")
    # The CLI opens its own sessions — the seed rows must be committed.
    await db_session.commit()

    embedder = EmbeddingService(HashEncoder())
    assert await backfill_embeddings.run(batch_size=2, embedder=embedder) == 3
    # Re-run: everything already embedded → zero work (idempotent/resumable).
    assert await backfill_embeddings.run(batch_size=2, embedder=embedder) == 0
