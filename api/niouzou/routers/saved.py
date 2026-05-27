"""Saved-articles endpoint: GET /saved."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from niouzou.deps import CurrentUser
from niouzou.schemas.feed import SavedResponse
from niouzou.services.saved_service import SavedService

router = APIRouter(prefix="/saved", tags=["saved"])

SavedServiceDep = Annotated[SavedService, Depends()]


@router.get("", response_model=SavedResponse)
async def list_saved(
    user: CurrentUser,
    service: SavedServiceDep,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
) -> SavedResponse:
    return await service.list_saved(user.id, cursor=cursor, limit=limit)
