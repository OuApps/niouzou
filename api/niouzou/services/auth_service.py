"""Authentication business logic: registration, login, token refresh."""

from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from niouzou.deps import SessionDep
from niouzou.errors import APIError, conflict, unauthorized
from niouzou.models import User
from niouzou.schemas.auth import AccessToken, TokenPair
from niouzou.security import (
    TOKEN_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class AuthService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    def _tokens_for(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def register(self, email: str, password: str) -> TokenPair:
        # E8-S1: the first user on a fresh instance is promoted to admin so the
        # self-hoster never has to flip the column manually.
        existing_admin = await self.session.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        )
        user = User(
            email=email,
            password_hash=hash_password(password),
            is_admin=not existing_admin,
        )
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            # Unique violation on email.
            raise conflict("Email already registered") from exc
        return self._tokens_for(user)

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.session.scalar(select(User).where(User.email == email))
        # Verify against the stored hash even when the user is missing would be
        # ideal for timing safety; for the MVP a clear invalid-credentials path
        # is enough.
        if user is None or not verify_password(password, user.password_hash):
            raise APIError(401, "invalid_credentials", "Invalid email or password")
        return self._tokens_for(user)

    async def refresh(self, refresh_token: str) -> AccessToken:
        try:
            user_id = decode_token(refresh_token, expected_type=TOKEN_REFRESH)
        except JWTError as exc:
            raise unauthorized("Invalid or expired refresh token") from exc

        user = await self.session.get(User, user_id)
        if user is None:
            raise unauthorized("User no longer exists")
        return AccessToken(access_token=create_access_token(user.id))
