"""Explore endpoints (E9-S3): GET /explore/history and GET /explore/new."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from niouzou.deps import CurrentUser
from niouzou.schemas.explore import (
    ExploreHistoryResponse,
    ExploreNewResponse,
    ExploreSearchResponse,
)
from niouzou.services.explore_service import ExploreService

router = APIRouter(prefix="/explore", tags=["explore"])

ExploreServiceDep = Annotated[ExploreService, Depends()]

# E11-S1 — filter bar in Explore. ``min_score`` and ``source_ids`` are both
# optional; ``min_score=0.0`` and an absent / empty ``source_ids`` list match
# the pre-filter behaviour. ``source_ids`` is capped to keep the IN clause
# bounded; UUIDs are validated by FastAPI, ownership is checked in the
# service so an unknown / cross-user id returns 422.
MinScoreQuery = Annotated[float, Query(ge=0.0, le=1.0)]
SourceIdsQuery = Annotated[list[uuid.UUID] | None, Query(max_length=20)]


@router.get("/history", response_model=ExploreHistoryResponse)
async def list_history(
    user: CurrentUser,
    service: ExploreServiceDep,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    min_score: MinScoreQuery = 0.0,
    source_ids: SourceIdsQuery = None,
) -> ExploreHistoryResponse:
    return await service.list_history(
        user.id,
        cursor=cursor,
        limit=limit,
        min_score=min_score,
        source_ids=source_ids,
    )


@router.get("/new", response_model=ExploreNewResponse)
async def list_new(
    user: CurrentUser,
    service: ExploreServiceDep,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    min_score: MinScoreQuery = 0.0,
    source_ids: SourceIdsQuery = None,
) -> ExploreNewResponse:
    return await service.list_new(
        user.id,
        cursor=cursor,
        limit=limit,
        min_score=min_score,
        source_ids=source_ids,
    )


@router.get("/search", response_model=ExploreSearchResponse)
async def search(
    user: CurrentUser,
    service: ExploreServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
) -> ExploreSearchResponse:
    """E17-S3 — text search across all the user's enriched articles."""
    return await service.search(user.id, q, cursor=cursor, limit=limit)
