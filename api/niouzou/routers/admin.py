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
from sqlalchemy import select, update

from niouzou.deps import CurrentAdmin, SessionDep
from niouzou.errors import APIError, not_found
from niouzou.models import User
from niouzou.schemas.admin import (
    AdminConfig,
    AdminConfigPatch,
    AdminModel,
    AdminPasswordReset,
    AdminUser,
)
from niouzou.security import hash_password
from niouzou.services.admin_models_service import fetch_models
from niouzou.services.settings_service import (
    OVERRIDABLE_KEYS,
    SettingsService,
    mask_api_key,
)

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("niouzou.admin")

# Default targets the Railway internal DNS for the refresh-worker service.
# Override locally with REFRESH_WORKER_URL=http://localhost:8001 etc.
_WORKER_URL = os.environ.get(
    "REFRESH_WORKER_URL", "http://refresh-worker.railway.internal:8000"
)

SettingsServiceDep = Annotated[SettingsService, Depends()]


def _config_response(effective) -> AdminConfig:  # type: ignore[no-untyped-def]
    return AdminConfig(
        openrouter_model=effective.openrouter_model,
        openrouter_api_key=mask_api_key(effective.openrouter_api_key),
        max_keywords_per_article=effective.max_keywords_per_article,
        cron_fetch_interval=effective.cron_fetch_interval,
        cron_refresh_weights_hour=effective.cron_refresh_weights_hour,
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
    return _config_response(effective)


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
        await service.set(key, value)
    effective = await service.get_effective()
    return _config_response(effective)


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


@router.post("/fix-users")
async def fix_users_admin(session: SessionDep) -> dict[str, str]:
    """Emergency endpoint to promote all users to admin (E8-S1 hotfix)."""
    await session.execute(update(User).values(is_admin=True))
    await session.commit()
    return {"status": "all_users_promoted_to_admin"}
