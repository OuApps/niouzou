"""System stats endpoint (GET /stats, E7-S15)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from niouzou.deps import CurrentUser
from niouzou.schemas.stats import Stats
from niouzou.services.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])

StatsServiceDep = Annotated[StatsService, Depends()]

# E10-S5 — closed set so the value can be fed safely into a Postgres
# ``interval`` literal without string interpolation; FastAPI returns 422 on
# any other value.
PipelineWindow = Literal["1h", "6h", "24h"]


@router.get("", response_model=Stats)
async def get_stats(
    user: CurrentUser,
    service: StatsServiceDep,
    pipeline_window: Annotated[PipelineWindow, Query()] = "6h",
) -> Stats:
    return await service.get(user.id, pipeline_window=pipeline_window)
