"""Sources endpoints: list, add, update, remove."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status

from niouzou.deps import CurrentUser
from niouzou.schemas.sources import (
    SourceCreate,
    SourceOut,
    SourcesListResponse,
    SourceUpdate,
)
from niouzou.schemas.tags import SourceTagsUpdate
from niouzou.services.sources_service import SourcesService
from niouzou.services.worker_client import trigger_pipeline_run

router = APIRouter(prefix="/sources", tags=["sources"])

SourcesServiceDep = Annotated[SourcesService, Depends()]


@router.get("", response_model=SourcesListResponse)
async def list_sources(
    user: CurrentUser, service: SourcesServiceDep
) -> SourcesListResponse:
    return await service.list_sources(user.id)


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    user: CurrentUser,
    service: SourcesServiceDep,
    background: BackgroundTasks,
) -> SourceOut:
    source = await service.create_source(
        user.id, body.url, fetch_full_content=body.fetch_full_content
    )
    # E19-S4 — kick the pipeline so a brand-new user doesn't wait up to a full
    # fetch interval for their first articles. Runs after the response (so the
    # request's commit has landed and the worker sees the new source); the
    # worker debounces against any run already in flight.
    background.add_task(trigger_pipeline_run)
    return source


@router.patch("/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    user: CurrentUser,
    service: SourcesServiceDep,
) -> SourceOut:
    return await service.update_source(
        user.id,
        source_id,
        fetch_full_content=body.fetch_full_content,
        active=body.active,
    )


@router.put("/{source_id}/tags", response_model=SourceOut)
async def set_source_tags(
    source_id: uuid.UUID,
    body: SourceTagsUpdate,
    user: CurrentUser,
    service: SourcesServiceDep,
) -> SourceOut:
    # E24-S3 — set-semantics: the submitted list replaces the source's tags.
    return await service.set_source_tags(user.id, source_id, body.tag_ids)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    user: CurrentUser,
    service: SourcesServiceDep,
    hard: bool = False,
) -> None:
    # E13-S5: default path = pause (UI-facing). ``?hard=true`` is the hidden
    # escape hatch that wipes the source and every dependent row via FK
    # CASCADE — not exposed in the PWA, available via API for cleanup.
    if hard:
        await service.hard_delete_source(user.id, source_id)
    else:
        await service.deactivate_source(user.id, source_id)
