"""Keyword-weight endpoints: GET /keywords, PATCH /keywords/{term}."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

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
    return await service.set_weight(user.id, term, body.weight)
