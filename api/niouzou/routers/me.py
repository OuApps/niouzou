"""Current-user endpoint (GET /me, E7-S9)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from niouzou.deps import CurrentUser
from niouzou.schemas.me import Me
from niouzou.services.me_service import MeService

router = APIRouter(prefix="/me", tags=["me"])

MeServiceDep = Annotated[MeService, Depends()]


@router.get("", response_model=Me)
async def get_me(user: CurrentUser, service: MeServiceDep) -> Me:
    return await service.get(user.id)
