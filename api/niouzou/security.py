"""Password hashing and JWT encode/decode — pure functions, no DB.

Kept separate from the auth service so both the API and tests can use token
helpers without pulling in a session.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from niouzou.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TOKEN_ACCESS = "access"
TOKEN_REFRESH = "refresh"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _create_token(subject: UUID, token_type: str, expires: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        TOKEN_ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: UUID) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        TOKEN_REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: str) -> UUID:
    """Decode and validate a token, returning the user id (the ``sub`` claim).

    Raises ``JWTError`` on an invalid/expired token or a type mismatch.
    """
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise JWTError("unexpected token type")
    sub = payload.get("sub")
    if not sub:
        raise JWTError("missing subject")
    return UUID(sub)
