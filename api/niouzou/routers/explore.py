"""Explore endpoints (E9-S3): GET /explore/history and GET /explore/new."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from niouzou.deps import CurrentUser
from niouzou.schemas.explore import ExploreHistoryResponse, ExploreNewResponse
from niouzou.services.explore_service import ExploreService

router = APIRouter(prefix="/explore", tags=["explore"])

ExploreServiceDep = Annotated[ExploreService, Depends()]


@router.get("/history", response_model=ExploreHistoryResponse)
async def list_history(
    user: CurrentUser,
    service: ExploreServiceDep,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
) -> ExploreHistoryResponse:
    return await service.list_history(user.id, cursor=cursor, limit=limit)


@router.get("/new", response_model=ExploreNewResponse)
async def list_new(
    user: CurrentUser,
    service: ExploreServiceDep,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
) -> ExploreNewResponse:
    return await service.list_new(user.id, cursor=cursor, limit=limit)
