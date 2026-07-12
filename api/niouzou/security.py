"""Password hashing and JWT encode/decode — pure functions, no DB.

Kept separate from the auth service so both the API and tests can use token
helpers without pulling in a session.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from niouzou.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TOKEN_ACCESS = "access"
TOKEN_REFRESH = "refresh"

# Service account API keys (E22). A key is a high-entropy random token, so we
# fingerprint it with a plain SHA-256 — no need for a slow, salted password
# hash (bcrypt) whose cost would tax every MCP request. The ``nzk_`` prefix
# makes keys recognisable (and greppable in logs the operator controls).
API_KEY_PREFIX = "nzk_"


def generate_api_key() -> str:
    """A fresh service account token: ``nzk_`` + 43 url-safe base64 chars."""
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hex of the raw token — what we persist and match against."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def api_key_prefix(raw_key: str) -> str:
    """Display-only fingerprint: ``nzk_`` + the first 8 body chars."""
    return raw_key[: len(API_KEY_PREFIX) + 8]


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
