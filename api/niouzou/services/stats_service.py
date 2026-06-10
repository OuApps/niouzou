"""Stats aggregator (GET /stats, E7-S15, E10-S1).

Per-user counts (articles, sources, keywords, enrichment) come from existing
tables scoped via the user→source→article ownership chain. The ``pipeline``
block is global: the refresh worker is single-replica and the
``pipeline_runs`` history is shared by the whole instance.
"""

import uuid

from sqlalchemy import case, func, select, text

from niouzou.deps import SessionDep
from niouzou.models import (
    Article,
    ArticleFeedback,  # noqa: F401  (kept for future enrichment stats)
    ArticleKeyword,
    CompactionRun,
    KeywordWeight,
    PipelineRun,
    Source,
)
from niouzou.models.compaction_run import STATUS_APPLIED, STATUS_PREVIEW
from niouzou.models.article import STATUS_ENRICHED
from niouzou.models.pipeline_run import STATUS_COMPLETED, STATUS_RUNNING
from niouzou.schemas.stats import (
    ArticlesStats,
    EnrichmentStats,
    KeywordsStats,
    PipelineAggregates,
    PipelineProgress,
    PipelineStats,
    SourcesStats,
    Stats,
)
from niouzou.services.settings_service import SettingsService

# E10-S5 — closed mapping from the validated ``pipeline_window`` query value
# to its Postgres interval literal. The router already restricts the input
# via a Literal type, but we keep the mapping here so the service can be
# called from tests with the same contract.
_PIPELINE_WINDOWS: dict[str, str] = {
    "1h": "1 hour",
    "6h": "6 hours",
    "24h": "24 hours",
}


async def embedding_counts(session) -> tuple[int, int]:
    """(articles with an embedding, articles total) — instance-wide.

    Surfaced in ``GET /admin/config`` (E16-S4) so the admin can judge
    whether a backfill is worth running before switching to Smart Match.
    """
    done, total = (
        await session.execute(
            select(
                func.count(Article.embedding),
                func.count(),
            ).select_from(Article)
        )
    ).one()
    return done, total


class StatsService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get(
        self, user_id: uuid.UUID, *, pipeline_window: str = "6h"
    ) -> Stats:
        # E8-S3: the PWA renders "Next run" against this value, so read it
        # via SettingsService — admin overrides via PATCH /admin/config flow
        # through immediately.
        settings_svc = SettingsService(self.session)
        fetch_interval = await settings_svc.get("cron_fetch_interval")
        # E11-S1 — surface the effective SCORE_THRESHOLD so the Explore
        # filter bar can render the "≥ seuil" chip without hardcoding it.
        score_threshold = await settings_svc.get("score_threshold")
        # ── Articles (scoped to user's sources, ignoring soft-deleted) ────
        article_join = (
            select(Article)
            .join(Source, Source.id == Article.source_id)
            .where(Source.user_id == user_id, Source.deleted_at.is_(None))
        ).subquery()

        articles_row = (
            await self.session.execute(
                select(
                    func.count().label("total"),
                    func.count(
                        case(
                            (article_join.c.status != STATUS_ENRICHED, 1)
                        )
                    ).label("pending"),
                    func.max(article_join.c.created_at).label("last_fetched_at"),
                    func.max(article_join.c.enriched_at).label("last_enriched_at"),
                    func.count(
                        case((article_join.c.enrichment_method == "ai", 1))
                    ).label("total_ai"),
                    func.count(
                        case((article_join.c.enrichment_method == "tfidf", 1))
                    ).label("total_tfidf"),
                    func.count(
                        case(
                            (
                                (article_join.c.enrichment_method == "tfidf")
                                & (article_join.c.enrichment_error.is_not(None)),
                                1,
                            )
                        )
                    ).label("total_tfidf_fallback"),
                ).select_from(article_join)
            )
        ).one()

        # ── Last enrichment error (most recent non-null, ≤ 1 h old) ────────
        # ``articles.enrichment_error`` is per-article and persists until the
        # row is re-enriched — without the time window an error from 3 h ago
        # would still flag the System panel as broken even after a dozen
        # healthy runs. 1 h matches the typical ``cron_fetch_interval`` (15
        # min) × ~4 runs of recovery time: long enough to be diagnostic, short
        # enough not to be noise. Recurring errors will keep being detected on
        # each new failed enrichment.
        last_err_row = (
            await self.session.execute(
                select(
                    article_join.c.enrichment_error,
                    article_join.c.enriched_at,
                )
                .where(article_join.c.enrichment_error.is_not(None))
                .where(
                    article_join.c.enriched_at
                    > func.now() - text("interval '1 hour'")
                )
                .order_by(article_join.c.enriched_at.desc())
                .limit(1)
            )
        ).first()

        # ── Sources ────────────────────────────────────────────────────────
        sources_total = await self.session.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.user_id == user_id, Source.deleted_at.is_(None))
        )
        # "active" mirrors total today — no per-source disable flag yet. Kept
        # as a separate field in the response so the PWA contract doesn't
        # change when that distinction is introduced.
        sources_active = sources_total

        # ── Keywords ───────────────────────────────────────────────────────
        keywords_row = (
            await self.session.execute(
                select(
                    func.count().label("total"),
                    func.count(
                        case((KeywordWeight.manually_overridden.is_(True), 1))
                    ).label("overridden"),
                ).where(KeywordWeight.user_id == user_id)
            )
        ).one()

        # ── Compaction telemetry (global, E10-S3) ─────────────────────────
        distinct_keyword_count = (
            await self.session.scalar(
                select(func.count(func.distinct(ArticleKeyword.term)))
            )
        ) or 0
        last_compact_at = await self.session.scalar(
            select(func.max(CompactionRun.applied_at)).where(
                CompactionRun.status == STATUS_APPLIED
            )
        )
        pending_preview_id = await self.session.scalar(
            select(CompactionRun.id)
            .where(CompactionRun.status == STATUS_PREVIEW)
            .order_by(CompactionRun.created_at.desc())
            .limit(1)
        )

        # ── Pipeline (global, E10-S1 + E10-S5 windowed aggregates) ────────
        pipeline = await self._latest_pipeline(pipeline_window)

        return Stats(
            cron_fetch_interval_minutes=int(fetch_interval or 15),
            score_threshold=float(score_threshold or 0.0),
            articles=ArticlesStats(
                total=articles_row.total or 0,
                pending_enrichment=articles_row.pending or 0,
                last_fetched_at=articles_row.last_fetched_at,
            ),
            sources=SourcesStats(
                total=sources_total or 0,
                active=sources_active or 0,
            ),
            keywords=KeywordsStats(
                total=keywords_row.total or 0,
                manually_overridden=keywords_row.overridden or 0,
                distinct_keyword_count=distinct_keyword_count,
                last_compact_at=last_compact_at,
                pending_compaction_id=(
                    str(pending_preview_id) if pending_preview_id else None
                ),
            ),
            enrichment=EnrichmentStats(
                last_enriched_at=articles_row.last_enriched_at,
                total_ai=articles_row.total_ai or 0,
                total_tfidf=articles_row.total_tfidf or 0,
                total_tfidf_fallback=articles_row.total_tfidf_fallback or 0,
                last_error=last_err_row.enrichment_error if last_err_row else None,
                last_error_at=last_err_row.enriched_at if last_err_row else None,
            ),
            pipeline=pipeline,
        )

    async def _latest_pipeline(self, window: str) -> PipelineStats:
        """Read the most recent ``pipeline_runs`` row, or a synthetic neverrun.

        ``in_progress`` is populated only when the latest run is still
        ``'running'`` — outside that window the PWA shows the last result
        instead of a progress bar.

        On upgrade from a pre-E10-S1 instance the table is empty until the
        first new cron tick (≤ ``cron_fetch_interval`` minutes after worker
        restart). ``status='never_run'`` is returned in that window — the
        PWA falls back to ``articles.last_fetched_at`` so the System panel
        isn't a wall of dashes during that transient gap.

        ``window`` selects the lookback for the E10-S5 windowed aggregates
        (``"1h"``/``"6h"``/``"24h"``); the value is mapped to a Postgres
        interval via the closed ``_PIPELINE_WINDOWS`` table so no raw user
        string ever lands inside the SQL.
        """
        aggregates = await self._pipeline_aggregates(window)
        row = await self.session.scalar(
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(1)
        )
        if row is None:
            return PipelineStats(
                status="never_run",
                started_at=None,
                completed_at=None,
                articles_fetched=0,
                articles_enriched=0,
                articles_failed=0,
                total_duration_s=None,
                avg_s_per_article=None,
                error=None,
                in_progress=None,
                aggregates=aggregates,
            )
        in_progress = None
        if row.status == STATUS_RUNNING:
            done = (row.articles_enriched or 0) + (row.articles_failed or 0)
            in_progress = PipelineProgress(
                done=done,
                total=row.articles_in_run or 0,
            )
        return PipelineStats(
            status=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            articles_fetched=row.articles_fetched or 0,
            articles_enriched=row.articles_enriched or 0,
            articles_failed=row.articles_failed or 0,
            total_duration_s=row.total_duration_s,
            avg_s_per_article=row.avg_s_per_article,
            error=row.error,
            in_progress=in_progress,
            aggregates=aggregates,
        )

    async def _pipeline_aggregates(self, window: str) -> PipelineAggregates:
        """Sum pipeline_runs over the requested window (E10-S5).

        Only ``status='completed'`` runs feed the aggregates: a
        ``'running'`` row has incomplete counters and a ``'failed'`` row
        usually has zero duration, so including either would skew the
        weighted ``avg_s_per_article``. The PWA still shows a live progress
        bar above the aggregates block for the in-flight run.
        """
        interval = _PIPELINE_WINDOWS[window]
        # ``text(f"interval '{interval}'")`` is safe because ``interval``
        # comes from the closed _PIPELINE_WINDOWS table — never from user
        # input directly.
        row = (
            await self.session.execute(
                select(
                    func.count().label("runs_count"),
                    func.coalesce(
                        func.sum(PipelineRun.articles_fetched), 0
                    ).label("articles_fetched"),
                    func.coalesce(
                        func.sum(PipelineRun.articles_enriched), 0
                    ).label("articles_enriched"),
                    func.coalesce(
                        func.sum(PipelineRun.articles_failed), 0
                    ).label("articles_failed"),
                    # Weighted average: sum(duration) / sum(articles). A run
                    # with 10 articles at 30 s contributes 10× more than a
                    # run with 1 article at 60 s, which is what we want.
                    (
                        func.nullif(func.sum(PipelineRun.total_duration_s), 0)
                        / func.nullif(func.sum(PipelineRun.articles_enriched), 0)
                    ).label("avg_s_per_article"),
                )
                .where(PipelineRun.status == STATUS_COMPLETED)
                .where(
                    PipelineRun.started_at
                    > func.now() - text(f"interval '{interval}'")
                )
            )
        ).one()
        return PipelineAggregates(
            window_hours=int(window.rstrip("h")),
            runs_count=row.runs_count or 0,
            articles_fetched=row.articles_fetched or 0,
            articles_enriched=row.articles_enriched or 0,
            articles_failed=row.articles_failed or 0,
            avg_s_per_article=(
                float(row.avg_s_per_article)
                if row.avg_s_per_article is not None
                else None
            ),
        )
