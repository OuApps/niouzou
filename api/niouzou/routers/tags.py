"""Tags endpoints (E24-S2): per-user CRUD + per-tag threshold."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from niouzou.deps import CurrentUser
from niouzou.schemas.tags import TagCreate, TagOut, TagsListResponse, TagUpdate
from niouzou.services.tags_service import TagsService

router = APIRouter(prefix="/tags", tags=["tags"])

TagsServiceDep = Annotated[TagsService, Depends()]


@router.get("", response_model=TagsListResponse)
async def list_tags(
    user: CurrentUser, service: TagsServiceDep
) -> TagsListResponse:
    return await service.list_tags(user.id)


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate, user: CurrentUser, service: TagsServiceDep
) -> TagOut:
    return await service.create_tag(
        user.id, body.name, threshold=body.threshold
    )


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: uuid.UUID,
    body: TagUpdate,
    user: CurrentUser,
    service: TagsServiceDep,
) -> TagOut:
    return await service.update_tag(user.id, tag_id, body)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID, user: CurrentUser, service: TagsServiceDep
) -> None:
    await service.delete_tag(user.id, tag_id)
