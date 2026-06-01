"""Keyword-compaction run telemetry (E10-S3).

One row per "merge aliases under a canonical term" cycle:

* `status='preview'` — the LLM proposed groups; nothing in `article_keywords`
  has been touched yet. The admin sees the list and can apply or reject.
* `status='applied'` — `article_keywords` updated, `keyword_weights`
  recomputed via `cron_refresh_weights`, alias orphans purged.
* `status='rejected'` — admin clicked cancel; the preview is housekeeping.
* `status='failed'` — exception raised during apply; `error` holds the trace
  summary.

Semantically distinct from `pipeline_runs` (which captures fetch+enrich
cycles), so they live in separate tables — sharing one would force columns
like `articles_fetched` to be NULL on every compaction row.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base

STATUS_PREVIEW = "preview"
STATUS_APPLIED = "applied"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"


class CompactionRun(Base):
    __tablename__ = "compaction_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    # ``[{"canonical": "...", "aliases": [...], "skipped_reason": "..."?}]``.
    # ``skipped_reason`` is annotated at apply time on groups whose canonical
    # or aliases include a ``manually_overridden=true`` term — those groups
    # are kept in the JSON for traceability but skipped during the UPDATE.
    groups_json: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    keywords_merged: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
