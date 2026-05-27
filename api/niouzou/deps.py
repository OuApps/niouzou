"""Shared FastAPI dependencies: DB session and the current authenticated user."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.db import get_session
from niouzou.errors import unauthorized
from niouzou.models import User
from niouzou.security import TOKEN_ACCESS, decode_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# auto_error=False so we emit the spec's {error, message} envelope ourselves.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        user_id = decode_token(credentials.credentials, expected_type=TOKEN_ACCESS)
    except JWTError as exc:
        raise unauthorized("Invalid or expired token") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized("User no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
