"""OpenRouter LLM usage log (E10-S7, per-usage split E21-S8).

One row per successful OpenRouter chat completion — from the enrichment
pipeline (``crons/enrich.py:enrichment_resources``) or the article chat
(``services/chat_service.py``), told apart by ``usage``. ``/stats`` sums
``cost_usd`` over 1h/6h/24h windows for the System panel's "OpenRouter
bill" display, with a per-usage breakdown.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    model: Mapped[str] = mapped_column(String, nullable=False)
    # E21-S8 — what spent the money: 'enrichment' (cron/worker) or 'chat'
    # (article chat). Lets /stats break the OpenRouter bill down per usage.
    usage: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'enrichment'")
    )
    cost_usd: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
