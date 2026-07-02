"""Admin endpoints.

The router groups three concerns:

* ``POST /admin/refresh`` (E7-S16) — proxies to the ``refresh-worker``
  service so the heavy fetch+enrich pipeline doesn't run inside the API
  process. The worker owns the single-in-flight lock.
* ``GET|PATCH /admin/config`` and ``GET /admin/models`` (E8-S3) — runtime
  configuration the admin can tune without a redeploy.
* ``GET /admin/users`` and ``PATCH /admin/users/{id}/password`` (E8-S5) —
  basic user administration.

Every route here is guarded by ``CurrentAdmin``: non-admin users receive
403.
"""

import logging
import os
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from niouzou.deps import CurrentAdmin, SessionDep
from niouzou.errors import APIError, not_found
from niouzou.models import CompactionRun, User
from niouzou.models.compaction_run import STATUS_PREVIEW
from niouzou.schemas.admin import (
    AdminConfig,
    AdminConfigPatch,
    AdminModel,
    AdminPasswordReset,
    AdminUser,
    CompactionApplyRequest,
    CompactionPreview,
    LlmPromptOut,
    LlmPromptUpdate,
)
from niouzou.security import hash_password
from niouzou.services.admin_models_service import fetch_models
from niouzou.services.llm_prompts_service import LlmPromptsServiceDep
from niouzou.services.settings_service import (
    OVERRIDABLE_KEYS,
    InvalidSettingError,
    SettingsService,
    mask_api_key,
)
from niouzou.services.stats_service import embedding_counts

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("niouzou.admin")

# Default targets the Railway internal DNS for the refresh-worker service.
# Override locally with REFRESH_WORKER_URL=http://localhost:8001 etc.
_WORKER_URL = os.environ.get(
    "REFRESH_WORKER_URL", "http://refresh-worker.railway.internal:8000"
)

SettingsServiceDep = Annotated[SettingsService, Depends()]


def _config_response(  # type: ignore[no-untyped-def]
    effective, embeddings_done: int, articles_total: int
) -> AdminConfig:
    return AdminConfig(
        openrouter_model=effective.openrouter_model,
        openrouter_api_key=mask_api_key(effective.openrouter_api_key),
        max_keywords_per_article=effective.max_keywords_per_article,
        cron_fetch_interval=effective.cron_fetch_interval,
        cron_nightly_refresh_hour=effective.cron_nightly_refresh_hour,
        score_threshold=effective.score_threshold,
        random_surface_rate=effective.random_surface_rate,
        enrichment_input_max_chars=effective.enrichment_input_max_chars,
        scoring_mode=effective.scoring_mode,
        embeddings_done=embeddings_done,
        articles_total=articles_total,
    )


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED)
async def trigger_refresh(_: CurrentAdmin) -> JSONResponse:
    """Forward the refresh request to the worker service.

    Mirrors the worker's response shape (``{"status": "started"|"already_running"}``)
    so the PWA contract doesn't change.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_WORKER_URL}/run")
        resp.raise_for_status()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED, content=resp.json()
        )
    except httpx.HTTPError as exc:
        logger.warning("admin/refresh: worker unreachable — %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "worker_unavailable"},
        )


@router.get("/config", response_model=AdminConfig)
async def get_config(
    _: CurrentAdmin, service: SettingsServiceDep
) -> AdminConfig:
    effective = await service.get_effective()
    done, total = await embedding_counts(service.session)
    return _config_response(effective, done, total)


@router.patch("/config", response_model=AdminConfig)
async def patch_config(
    body: AdminConfigPatch,
    _: CurrentAdmin,
    service: SettingsServiceDep,
) -> AdminConfig:
    # ``model_dump(exclude_unset=True)`` so an omitted field is left untouched
    # while an explicit ``null`` or empty string clears the override.
    payload = body.model_dump(exclude_unset=True)
    for key, value in payload.items():
        if key not in OVERRIDABLE_KEYS:
            raise APIError(400, "bad_request", f"Unknown setting: {key}")
        try:
            await service.validate(key, value)
        except InvalidSettingError as exc:
            raise APIError(422, "validation_error", str(exc))
        await service.set(key, value)
    effective = await service.get_effective()
    done, total = await embedding_counts(service.session)
    return _config_response(effective, done, total)


@router.get("/models", response_model=list[AdminModel])
async def get_models(
    _: CurrentAdmin, service: SettingsServiceDep
) -> list[AdminModel]:
    api_key = await service.get("openrouter_api_key")
    return await fetch_models(api_key if isinstance(api_key, str) else None)


@router.get("/users", response_model=list[AdminUser])
async def list_users(
    _: CurrentAdmin, session: SessionDep
) -> list[AdminUser]:
    rows = (
        await session.execute(
            select(User.id, User.email, User.is_admin, User.created_at).order_by(
                User.created_at.asc()
            )
        )
    ).all()
    return [
        AdminUser(
            id=str(row.id),
            email=row.email,
            is_admin=row.is_admin,
            created_at=row.created_at,
        )
        for row in rows
    ]


# ── E10-S3 — Keyword compaction (proxies to refresh-worker) ──────────────


@router.post(
    "/compact-keywords/preview",
    response_model=CompactionPreview,
    status_code=status.HTTP_202_ACCEPTED,
)
async def compact_keywords_preview(_: CurrentAdmin) -> JSONResponse:
    """Ask the worker to propose a keyword-merge plan.

    Same proxy pattern as ``POST /admin/refresh`` — the LLM call and DB write
    happen on the refresh-worker so uvicorn isn't blocked while the model
    thinks. Returns the preview id + groups so the PWA can render the
    confirmation modal.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{_WORKER_URL}/compact/preview")
        resp.raise_for_status()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED, content=resp.json()
        )
    except httpx.HTTPError as exc:
        logger.warning("admin/compact-keywords/preview: worker unreachable — %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "worker_unavailable"},
        )


@router.get(
    "/compact-keywords/{run_id}",
    response_model=CompactionPreview,
)
async def compact_keywords_get(
    run_id: uuid.UUID, _: CurrentAdmin, session: SessionDep
) -> CompactionPreview:
    """Return a previously-generated preview so the admin can resume it.

    Read straight from the DB — no worker proxy or LLM call. Used by the
    PWA's "Reprendre la dernière analyse" affordance when
    ``stats.keywords.pending_compaction_id`` is non-null at mount time.
    Only previews are surfaceable; already-applied or rejected runs return
    404 so the UI can't offer a no-op confirm.
    """
    run = await session.get(CompactionRun, run_id)
    if run is None or run.status != STATUS_PREVIEW:
        raise not_found("Compaction preview not found")
    return CompactionPreview(id=str(run.id), groups=run.groups_json)


@router.post(
    "/compact-keywords/apply", status_code=status.HTTP_202_ACCEPTED
)
async def compact_keywords_apply(
    body: CompactionApplyRequest, _: CurrentAdmin
) -> JSONResponse:
    """Apply a previously-generated preview. Fire-and-forget on the worker.

    The worker now pre-validates the run id, so 404 / 409 are passed through
    untouched — the PWA gets a real error instead of a phantom 202.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_WORKER_URL}/compact/apply", json={"id": body.id}
            )
        # Forward 4xx from the worker as-is (e.g. 404 unknown id, 409 already
        # applied). Only 5xx / transport errors fall through to the 503 below.
        if resp.status_code >= 500:
            resp.raise_for_status()
        return JSONResponse(
            status_code=resp.status_code, content=resp.json()
        )
    except httpx.HTTPError as exc:
        logger.warning("admin/compact-keywords/apply: worker unreachable — %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "worker_unavailable"},
        )


@router.delete(
    "/compact-keywords/{run_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def compact_keywords_reject(
    run_id: uuid.UUID, _: CurrentAdmin
) -> JSONResponse:
    """Reject a pending preview so it stops showing as actionable."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(f"{_WORKER_URL}/compact/{run_id}")
        # 204 No Content has no body — pass the status through unchanged.
        return JSONResponse(status_code=resp.status_code, content=None)
    except httpx.HTTPError as exc:
        logger.warning("admin/compact-keywords/reject: worker unreachable — %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "worker_unavailable"},
        )


@router.patch(
    "/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT
)
async def reset_password(
    user_id: uuid.UUID,
    body: AdminPasswordReset,
    _: CurrentAdmin,
    session: SessionDep,
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise not_found("User not found")
    user.password_hash = hash_password(body.new_password)


@router.get("/prompts", response_model=list[LlmPromptOut])
async def list_prompts(
    _: CurrentAdmin, service: LlmPromptsServiceDep
) -> list[LlmPromptOut]:
    rows = await service.list_all()
    return [LlmPromptOut.model_validate(r) for r in rows]


@router.patch("/prompts/{name}", response_model=LlmPromptOut)
async def update_prompt(
    name: str,
    body: LlmPromptUpdate,
    _: CurrentAdmin,
    service: LlmPromptsServiceDep,
) -> LlmPromptOut:
    row = await service.update(name, body.body)
    return LlmPromptOut.model_validate(row)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    admin: CurrentAdmin,
    session: SessionDep,
) -> None:
    """Hard-delete a user and every dependent row via FK CASCADE (E13-S3).

    Refuses self-deletion to avoid an admin locking themselves out — they
    have to ask another admin (or unbrick via direct DB access).
    """
    if user_id == admin.id:
        raise APIError(400, "bad_request", "Cannot delete your own account")
    user = await session.get(User, user_id)
    if user is None:
        raise not_found("User not found")
    await session.delete(user)
