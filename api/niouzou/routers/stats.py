"""System stats endpoint (GET /stats, E7-S15)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from niouzou.deps import CurrentAdmin, CurrentUser
from niouzou.schemas.stats import FeedFreshness, Stats
from niouzou.services.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])

StatsServiceDep = Annotated[StatsService, Depends()]

# E10-S5 — closed set so the value can be fed safely into a Postgres
# ``interval`` literal without string interpolation; FastAPI returns 422 on
# any other value.
PipelineWindow = Literal["1h", "6h", "24h"]


@router.get("", response_model=Stats)
async def get_stats(
    admin: CurrentAdmin,
    service: StatsServiceDep,
    pipeline_window: Annotated[PipelineWindow, Query()] = "6h",
) -> Stats:
    # E19-S7 — admin-only: this payload is global instance telemetry
    # (pipeline health, enrichment queue, OpenRouter bill). Non-admins get
    # the lightweight ``/stats/freshness`` slice instead.
    return await service.get(admin.id, pipeline_window=pipeline_window)


@router.get("/freshness", response_model=FeedFreshness)
async def get_feed_freshness(
    user: CurrentUser,
    service: StatsServiceDep,
) -> FeedFreshness:
    # E19-S7 — minimal "is new content on its way?" signal for every user;
    # no cost, no errors, no run trigger.
    return await service.freshness(user.id)
