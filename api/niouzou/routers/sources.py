"""Sources endpoints: list, add, update, remove."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from niouzou.deps import CurrentUser
from niouzou.schemas.sources import (
    SourceCreate,
    SourceOut,
    SourcesListResponse,
    SourceUpdate,
)
from niouzou.services.sources_service import SourcesService

router = APIRouter(prefix="/sources", tags=["sources"])

SourcesServiceDep = Annotated[SourcesService, Depends()]


@router.get("", response_model=SourcesListResponse)
async def list_sources(
    user: CurrentUser, service: SourcesServiceDep
) -> SourcesListResponse:
    return await service.list_sources(user.id)


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate, user: CurrentUser, service: SourcesServiceDep
) -> SourceOut:
    return await service.create_source(
        user.id, body.url, fetch_full_content=body.fetch_full_content
    )


@router.patch("/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    user: CurrentUser,
    service: SourcesServiceDep,
) -> SourceOut:
    return await service.update_source(
        user.id, source_id, fetch_full_content=body.fetch_full_content
    )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID, user: CurrentUser, service: SourcesServiceDep
) -> None:
    await service.delete_source(user.id, source_id)
