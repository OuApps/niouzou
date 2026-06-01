"""Pipeline run telemetry (E10-S1).

One row per fetch+enrich cycle driven by the refresh worker. The worker
inserts a ``status='running'`` row at the start of each cycle, increments
counters as articles are enriched, and finalises the row to ``'completed'``
or ``'failed'`` at the end.

``/stats`` reads the most recent row to render the System panel — see
``StatsService`` for the lifecycle-aware "stalled" detection that replaced
the old heuristic on ``article.created_at``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    articles_fetched: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    articles_enriched: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    articles_failed: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    # Snapshot of pending articles taken at the start of the enrich loop.
    # Frozen so the PWA progress bar denominator doesn't drift if a concurrent
    # fetch lands new pending rows mid-run.
    articles_in_run: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    total_duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_s_per_article: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
