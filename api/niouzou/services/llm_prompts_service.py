"""Read/write the LLM prompts stored in ``llm_prompts`` (E13-S2).

Two entry points:

* ``load_all_into_dict`` — used by the pipeline at run start to snapshot
  every prompt into a plain ``dict[name, body]``. Sync code paths
  (``EnrichmentService.generate_enrichment`` runs in
  ``asyncio.to_thread``) can then read by name without awaiting.

* ``LlmPromptsService.list_all`` / ``get`` / ``update`` — used by the
  admin router. ``update`` returns the row so the PWA can show the new
  ``updated_at`` without a second roundtrip.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.deps import SessionDep
from niouzou.errors import not_found
from niouzou.models import LlmPrompt


async def load_all_into_dict(session: AsyncSession) -> dict[str, str]:
    rows = await session.scalars(select(LlmPrompt))
    return {p.name: p.body for p in rows.all()}


class LlmPromptsService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def list_all(self) -> list[LlmPrompt]:
        rows = await self.session.scalars(
            select(LlmPrompt).order_by(LlmPrompt.name.asc())
        )
        return list(rows.all())

    async def get(self, name: str) -> LlmPrompt:
        row = await self.session.get(LlmPrompt, name)
        if row is None:
            raise not_found(f"Unknown LLM prompt: {name}")
        return row

    async def update(self, name: str, body: str) -> LlmPrompt:
        row = await self.get(name)
        row.body = body
        await self.session.flush()
        return row


LlmPromptsServiceDep = Annotated[LlmPromptsService, Depends()]
