"""Auth endpoints: register, login, refresh."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from niouzou.schemas.auth import (
    AccessToken,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from niouzou.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

AuthServiceDep = Annotated[AuthService, Depends()]


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, service: AuthServiceDep) -> TokenPair:
    return await service.register(body.email, body.password)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, service: AuthServiceDep) -> TokenPair:
    return await service.login(body.email, body.password)


@router.post("/refresh", response_model=AccessToken)
async def refresh(body: RefreshRequest, service: AuthServiceDep) -> AccessToken:
    return await service.refresh(body.refresh_token)
