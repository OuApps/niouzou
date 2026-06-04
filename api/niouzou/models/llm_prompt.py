from datetime import datetime

from sqlalchemy import DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class LlmPrompt(Base):
    """Admin-editable LLM system prompt (E13-S2).

    Replaces the hardcoded constants previously sitting in
    ``enrichment_service``, ``compaction_service`` and
    ``scoring/ai_keyword``. Loaded once per pipeline run (admin overrides
    apply on the next run, not mid-flight) and surfaced read/write in
    ``/admin/prompts``.
    """

    __tablename__ = "llm_prompts"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )
