"""System stats endpoint (GET /stats, E7-S15)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from niouzou.deps import CurrentUser
from niouzou.schemas.stats import Stats
from niouzou.services.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])

StatsServiceDep = Annotated[StatsService, Depends()]


@router.get("", response_model=Stats)
async def get_stats(user: CurrentUser, service: StatsServiceDep) -> Stats:
    return await service.get(user.id)
