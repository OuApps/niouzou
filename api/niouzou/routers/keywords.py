"""Keyword-weight endpoints: GET /keywords, PATCH /keywords/{term},
DELETE /keywords."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from niouzou.deps import CurrentUser
from niouzou.schemas.keywords import KeywordOut, KeywordPatch, KeywordsResponse
from niouzou.services.keywords_service import KeywordsService

router = APIRouter(prefix="/keywords", tags=["keywords"])

KeywordsServiceDep = Annotated[KeywordsService, Depends()]


@router.get("", response_model=KeywordsResponse)
async def list_keywords(
    user: CurrentUser,
    service: KeywordsServiceDep,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> KeywordsResponse:
    return await service.list_keywords(user.id, cursor=cursor, limit=limit)


@router.patch("/{term}", response_model=KeywordOut)
async def patch_keyword(
    term: str, body: KeywordPatch, user: CurrentUser, service: KeywordsServiceDep
) -> KeywordOut:
    return await service.patch_keyword(
        user.id, term, body.weight, body.manually_overridden
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def reset_keywords(
    user: CurrentUser, service: KeywordsServiceDep
) -> Response:
    """Wipe all keyword weights for the current user. Irreversible."""
    await service.reset_all(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
