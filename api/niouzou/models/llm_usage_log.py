"""OpenRouter LLM usage log (E10-S7).

One row per successful OpenRouter chat completion (enrichment only — see
``crons/enrich.py:enrichment_resources``). ``/stats`` sums ``cost_usd`` over
1h/6h/24h windows for the System panel's "OpenRouter bill" display.
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
    cost_usd: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
