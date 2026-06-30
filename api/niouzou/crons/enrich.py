"""cron_enrich — extract content, summarise, score pending articles (E5).

Run with: ``uv run python -m niouzou.crons.enrich`` (or via the cron container).

Per pending article:
  1. Extract clean content with newspaper4k, falling back to the RSS body.
  2. Enrich via a single combined LLM call — ``summary_executive`` bullets +
     keywords when AI is on; neither when AI is off or the call fails
     (keyword extraction is LLM-only since E16-S8 — no TF-IDF fallback). The
     LLM sees both the RSS teaser and the fetched body (deduped + labeled),
     not one as a fallback for the other.
  3. Store the keywords when the LLM produced some.
  4. Compute and store the semantic embedding (local model, AI-independent).
  5. Score the article for its source's owner — BOTH methods at once
     (``keyword_score`` + ``smart_score``, E16-S8), whatever ``scoring_mode``.
  6. Mark the article ``enriched``.

Persistence and scoring maths are NOT reimplemented here — steps 3–5 delegate
to ScoringService (Epic 3). The cron only orchestrates and owns the article
status transition. An article that got neither keywords nor an embedding is
still ``enriched`` and surfaces (both scores NULL → treated as cold).

Per-user scoring scope (E5-S2 open item): an article belongs to exactly one
source, which belongs to exactly one user, and the feed only ever surfaces an
article to that source's owner. So we score for that single owner — who, by
construction, registered before the source existed.

E10-S1 — the refresh worker drives the pipeline loop directly (so it can
record per-article telemetry into ``pipeline_runs``); this module now exposes
``enrichment_resources()`` as a reusable context manager. ``run()`` is kept
for the CLI / one-shot invocation path and uses the same helper internally.

Each article is enriched in its own transaction so one failure can't roll back
a whole batch. Blocking network calls (newspaper, LLM) run off the event loop
via asyncio.to_thread.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.config import get_settings
from niouzou.db import session_scope
from niouzou.models import Article, ArticleKeyword, LLMUsageLog, Source
from niouzou.models.article import STATUS_ENRICHED, STATUS_PENDING
from niouzou.scoring import ScoringPipeline
from niouzou.scoring.smart_match import SmartMatchParams
from niouzou.services.embedding_service import (
    EmbeddingService,
    embedding_available,
    get_embedding_service,
)
from niouzou.services.enrichment_service import EnrichmentService
from niouzou.services.llm_prompts_service import load_all_into_dict
from niouzou.services.openrouter_client import OpenRouterClient
from niouzou.services.scoring_service import ScoringService
from niouzou.services.settings_service import SettingsService

logger = logging.getLogger("niouzou.cron_enrich")


@dataclass(slots=True)
class EnrichmentResources:
    """Services needed to enrich one article — built once per run."""

    enrichment: EnrichmentService
    scoring: ScoringService
    # OpenRouter model id snapshotted at the start of the run (E10-S2). Used
    # to stamp ``articles.enrichment_model`` when the LLM produced the
    # keywords; ``None`` when AI is disabled for this run.
    openrouter_model: str | None = None
    # E16-S2 — local embedding service; ``None`` when sentence-transformers
    # isn't installed (articles then keep embedding = NULL). The model itself
    # loads lazily on the first embed call, never here.
    embedder: EmbeddingService | None = None


async def _pending_article_ids(session: AsyncSession, limit: int) -> list[uuid.UUID]:
    """Oldest pending article ids first (FIFO enrichment)."""
    rows = await session.execute(
        select(Article.id)
        .where(Article.status == STATUS_PENDING)
        .order_by(Article.created_at)
        .limit(limit)
    )
    return list(rows.scalars().all())


# Top N existing keywords injected into every enrichment prompt for this run
# (E10-S2). 200 is a balance: enough to cover the main entities/domains the
# instance has seen, low enough to fit in the prompt budget (~1.5kB) and to
# stay under the prompt-cache hash boundary as the vocab grows.
_VOCAB_INJECTION_TOP_N = 200


async def _load_top_keywords(session: AsyncSession, limit: int) -> list[str]:
    """Most-frequent ``article_keywords.term`` strings, ordered by count desc.

    Called once per cron run; cached on ``EnrichmentService._vocab``. Empty
    list on a fresh instance is fine — the prompt just skips the line.
    """
    rows = await session.execute(
        select(ArticleKeyword.term)
        .group_by(ArticleKeyword.term)
        .order_by(func.count().desc(), ArticleKeyword.term.asc())
        .limit(limit)
    )
    return list(rows.scalars().all())


@asynccontextmanager
async def enrichment_resources() -> AsyncIterator[EnrichmentResources]:
    """Build the per-run enrichment services and close the LLM client on exit.

    Admin overrides are snapshotted once: a long pipeline run sees a consistent
    view even if the admin updates the DB mid-run. The refresh worker uses this
    directly to drive its per-article loop (E10-S1); ``cron_enrich.run()``
    wraps it for the CLI entry point.
    """
    async with session_scope() as cfg_session:
        effective = await SettingsService(cfg_session).get_effective()
        vocab = await _load_top_keywords(cfg_session, _VOCAB_INJECTION_TOP_N)
        # E13-S2 — snapshot the DB-backed prompts once per run. Admin
        # edits apply on the next pipeline tick rather than mid-flight,
        # so a long enrichment loop sees a consistent prompt.
        prompts = await load_all_into_dict(cfg_session)

    client = OpenRouterClient.from_overrides(
        effective.openrouter_api_key, effective.openrouter_model
    )
    enrichment = EnrichmentService(
        client, max_input_chars=effective.enrichment_input_max_chars
    )
    enrichment.set_vocab(vocab)
    if "enrichment.combined" in prompts:
        enrichment.set_system_prompt(prompts["enrichment.combined"])
    else:
        logger.warning(
            "cron_enrich: 'enrichment.combined' prompt missing from DB — "
            "falling back to the trimmed in-code constant"
        )
    # E16-S8 — a single ScoringService computes both scores. The pipeline is
    # only used for the pure relevance maths (Σ salience × weight, shared by
    # every scorer) — keyword *extraction* comes from the combined enrichment
    # call, never from here.
    scoring = ScoringService(
        ScoringPipeline(),
        max_keywords_per_article=effective.max_keywords_per_article,
        smart_params=SmartMatchParams(
            topk=effective.smart_topk,
            lambda_=effective.smart_lambda,
            beta=effective.smart_beta,
            decay_halflife_days=effective.smart_decay_halflife_days,
        ),
    )

    if embedding_available():
        embedder = get_embedding_service()
    else:
        embedder = None
        logger.warning(
            "cron_enrich: sentence-transformers not installed — articles "
            "will keep embedding = NULL (smart_score unavailable)"
        )

    logger.info(
        "cron_enrich: resources ready (ai_enabled=%s, model=%s, vocab_terms=%d, "
        "embeddings=%s)",
        enrichment.ai_enabled,
        effective.openrouter_model if client is not None else "n/a",
        len(vocab),
        "on" if embedder is not None else "off",
    )
    try:
        yield EnrichmentResources(
            enrichment=enrichment,
            scoring=scoring,
            openrouter_model=(
                effective.openrouter_model if client is not None else None
            ),
            embedder=embedder,
        )
    finally:
        if client is not None:
            await _flush_usage_log(client)
            client.close()


async def _flush_usage_log(client: OpenRouterClient) -> None:
    """Persist this run's OpenRouter usage records to ``llm_usage_log`` (E10-S7).

    One row per successful completion made through ``client`` during the
    run — ``/stats`` sums ``cost_usd`` over 1h/6h/24h for the System panel.

    Cost lookups are resolved here, at end of run, rather than inline after
    each completion: OpenRouter's ``/generation`` endpoint 404s for a few
    seconds while it finalises stats, so inline lookups always missed and the
    table stayed empty (E17-S1). Run in a thread — the lookups are blocking
    HTTP + a short retry sleep.
    """
    await asyncio.to_thread(client.resolve_pending_usage)
    if not client.usage_log:
        return
    async with session_scope() as session:
        for record in client.usage_log:
            session.add(
                LLMUsageLog(
                    model=record.model,
                    cost_usd=record.cost_usd,
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                )
            )
    client.usage_log.clear()


async def enrich_article(
    session: AsyncSession,
    article: Article,
    *,
    enrichment: EnrichmentService,
    scoring: ScoringService,
    openrouter_model: str | None = None,
    embedder: EmbeddingService | None = None,
) -> None:
    """Enrich a single article in the given (open) transaction.

    The AI path uses a single combined LLM call (summaries + keywords) via
    ``EnrichmentService.generate_enrichment``. On LLM failure (or AI off) no
    keywords are stored — ``keyword_score`` stays NULL (E16-S8); the embedding
    is local and still computed, so ``smart_score`` survives without AI.
    """
    owner_id = await session.scalar(
        select(Source.user_id).where(Source.id == article.source_id)
    )
    if owner_id is None:
        # Orphaned article (source deleted) — nothing to score for.
        logger.warning("enrich: no source owner for article %s, skipping", article.id)
        return

    # 1. Content extraction (blocking) off the event loop.
    t0 = time.perf_counter()
    logger.info("enrich[%s]: extracting content from %s", article.id, article.url)
    # The RSS teaser (publisher-written, clean, on-topic) is the article's
    # content at this point — captured before extraction overwrites it so the
    # LLM gets BOTH the teaser and the fetched body (anti-hallucination anchor),
    # not one as a mere fallback for the other.
    rss_teaser = article.content
    extracted = await asyncio.to_thread(
        enrichment.extract_content, article.url, rss_fallback=rss_teaser
    )
    logger.info(
        "enrich[%s]: content extracted (%d chars) in %.2fs",
        article.id,
        len(extracted.content or ""),
        time.perf_counter() - t0,
    )
    if extracted.content:
        article.content = extracted.content
    if extracted.og_image_url and not article.og_image_url:
        article.og_image_url = extracted.og_image_url

    # 2. Combined LLM call: summaries + keywords in one roundtrip.
    t0 = time.perf_counter()
    logger.info("enrich[%s]: generating enrichment (summaries + keywords)...", article.id)
    enriched = await asyncio.to_thread(
        enrichment.generate_enrichment,
        article.title,
        article.content,
        rss_teaser=rss_teaser,
    )
    logger.info(
        "enrich[%s]: enrichment generated in %.2fs (exec=%d, keywords=%s)",
        article.id,
        time.perf_counter() - t0,
        len(enriched.summary_executive or ""),
        len(enriched.keywords) if enriched.keywords is not None else "n/a",
    )
    article.summary_executive = enriched.summary_executive

    # 3. Keyword persistence — LLM-only (E16-S8). ``keywords is None`` signals
    # the LLM call itself failed (or AI is off); an empty list means it ran
    # cleanly but had nothing useful. Either way no keywords are stored and
    # the keyword method scores NULL for this article.
    if enriched.keywords:
        t0 = time.perf_counter()
        await scoring.store_keywords(session, article, enriched.keywords)
        method, ai_error = "ai", None
        logger.info(
            "enrich[%s]: %d keywords stored in %.2fs",
            article.id,
            len(enriched.keywords),
            time.perf_counter() - t0,
        )
    else:
        method = None
        if enriched.keywords is None and enrichment.ai_enabled:
            ai_error = "LLM enrichment call failed or returned no keywords"
            logger.warning(
                "enrich: AI enrichment unusable for %s — no keywords stored "
                "(keyword_score will be NULL)",
                article.id,
            )
        else:
            ai_error = None

    # 4. Semantic embedding (E16-S2) — local model, computed for every article
    # regardless of scoring_mode and of LLM availability. Stored (and flushed)
    # BEFORE scoring so the smart_score SELECT sees the fresh vector in the
    # same transaction (E16-S8). A failure leaves the column NULL
    # (smart_score = NULL for that row) instead of aborting the enrichment.
    if embedder is not None:
        t0 = time.perf_counter()
        try:
            article.embedding = await asyncio.to_thread(
                embedder.embed_article,
                article.title,
                article.summary_executive,
                article.content,
            )
            logger.info(
                "enrich[%s]: embedding computed in %.2fs",
                article.id,
                time.perf_counter() - t0,
            )
        except Exception:
            logger.exception(
                "enrich: embedding failed for %s — leaving NULL", article.id
            )
    await session.flush()

    # 5. Per-user scores, both methods at once (reads DB only, no LLM).
    t0 = time.perf_counter()
    await scoring.score_article_for_user(session, article.id, owner_id)
    logger.info(
        "enrich[%s]: keyword + smart scores computed in %.2fs",
        article.id,
        time.perf_counter() - t0,
    )

    # 6. Transition to enriched + record the active method/error (E7-S15).
    # ``enrichment_method`` / ``enrichment_model`` are populated only when the
    # LLM produced the keywords; a failed/disabled LLM leaves them NULL so the
    # debug panel doesn't mislabel the row as AI-enriched.
    article.status = STATUS_ENRICHED
    article.enriched_at = datetime.now(timezone.utc)
    article.enrichment_method = method
    article.enrichment_error = ai_error
    article.enrichment_model = openrouter_model if method == "ai" else None


async def run() -> int:
    """CLI entry point: enrich one batch of pending articles.

    The refresh worker no longer calls this — it drives its own loop with
    ``pipeline_runs`` telemetry (E10-S1). Kept here so the cron script and
    direct ``python -m niouzou.crons.enrich`` invocations still work.
    """
    settings = get_settings()
    logger.info(
        "cron_enrich: start (batch_size=%d)", settings.enrich_batch_size
    )
    async with enrichment_resources() as resources:
        async with session_scope() as session:
            pending_ids = await _pending_article_ids(
                session, settings.enrich_batch_size
            )

        if not pending_ids:
            logger.info("cron_enrich: no pending articles — done")
            return 0

        logger.info("cron_enrich: %d articles to enrich", len(pending_ids))
        enriched = 0
        batch_start = time.perf_counter()
        for idx, article_id in enumerate(pending_ids, start=1):
            t0 = time.perf_counter()
            logger.info(
                "cron_enrich: [%d/%d] starting article %s",
                idx,
                len(pending_ids),
                article_id,
            )
            try:
                async with session_scope() as session:
                    article = await session.get(Article, article_id)
                    if article is None or article.status != STATUS_PENDING:
                        logger.info(
                            "cron_enrich: [%d/%d] skipped (already handled)",
                            idx,
                            len(pending_ids),
                        )
                        continue
                    await enrich_article(
                        session,
                        article,
                        enrichment=resources.enrichment,
                        scoring=resources.scoring,
                        openrouter_model=resources.openrouter_model,
                        embedder=resources.embedder,
                    )
                    enriched += 1
                logger.info(
                    "cron_enrich: [%d/%d] done in %.2fs",
                    idx,
                    len(pending_ids),
                    time.perf_counter() - t0,
                )
            except Exception:
                # Isolate failures: a bad article must not abort the batch.
                logger.exception(
                    "cron_enrich: [%d/%d] failed to enrich article %s",
                    idx,
                    len(pending_ids),
                    article_id,
                )

        logger.info(
            "cron_enrich: done — enriched %d/%d articles in %.1fs",
            enriched,
            len(pending_ids),
            time.perf_counter() - batch_start,
        )
        return enriched


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
