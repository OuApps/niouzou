"""Feed endpoints: GET /feed and POST /feed/{article_id}/impression."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from niouzou.deps import CurrentUser
from niouzou.schemas.feed import FeedResponse
from niouzou.services.feed_service import FeedService

router = APIRouter(prefix="/feed", tags=["feed"])

FeedServiceDep = Annotated[FeedService, Depends()]


@router.get("", response_model=FeedResponse)
async def get_feed(
    user: CurrentUser,
    service: FeedServiceDep,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    # Per-request override of SCORE_THRESHOLD (E7-S8): the PWA empty-state
    # lowers it on demand so the user can see sub-threshold articles.
    min_score: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
) -> FeedResponse:
    return await service.get_feed(
        user.id, cursor=cursor, limit=limit, min_score=min_score
    )


@router.post(
    "/{article_id}/impression", status_code=status.HTTP_204_NO_CONTENT
)
async def record_impression(
    article_id: uuid.UUID, user: CurrentUser, service: FeedServiceDep
) -> None:
    await service.record_impression(user.id, article_id)
