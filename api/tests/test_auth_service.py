"""Authentication tests (E3-S2): register → login → refresh, error paths."""

import time

import pytest
from jose import JWTError

from niouzou.errors import APIError
from niouzou.security import (
    TOKEN_ACCESS,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from niouzou.services.auth_service import AuthService


def test_password_hash_roundtrips():
    h = hash_password("securepassword")
    assert h != "securepassword"
    assert verify_password("securepassword", h)
    assert not verify_password("wrong", h)


async def test_register_then_login(db_session):
    svc = AuthService(db_session)
    tokens = await svc.register("user@test.dev", "securepassword")
    await db_session.commit()
    assert tokens.access_token and tokens.refresh_token

    logged_in = await svc.login("user@test.dev", "securepassword")
    assert logged_in.access_token

    # The access token resolves back to a real user id.
    user_id = decode_token(logged_in.access_token, expected_type=TOKEN_ACCESS)
    assert user_id is not None


async def test_duplicate_email_conflicts(db_session):
    svc = AuthService(db_session)
    await svc.register("dup@test.dev", "securepassword")
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await svc.register("dup@test.dev", "securepassword")
    assert exc.value.status_code == 409


async def test_login_wrong_password_rejected(db_session):
    svc = AuthService(db_session)
    await svc.register("user2@test.dev", "securepassword")
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await svc.login("user2@test.dev", "nope")
    assert exc.value.status_code == 401


async def test_refresh_issues_new_access_token(db_session):
    svc = AuthService(db_session)
    tokens = await svc.register("user3@test.dev", "securepassword")
    await db_session.commit()

    refreshed = await svc.refresh(tokens.refresh_token)
    assert refreshed.access_token


async def test_refresh_rejects_access_token(db_session):
    svc = AuthService(db_session)
    tokens = await svc.register("user4@test.dev", "securepassword")
    await db_session.commit()

    # An access token is not a valid refresh token.
    with pytest.raises(APIError):
        await svc.refresh(tokens.access_token)


def test_expired_token_is_rejected(monkeypatch):
    from niouzou import config, security

    config.get_settings.cache_clear()
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "-1")  # already expired
    config.get_settings.cache_clear()
    import uuid

    token = create_access_token(uuid.uuid4())
    time.sleep(0.01)
    with pytest.raises(JWTError):
        decode_token(token, expected_type=security.TOKEN_ACCESS)
    config.get_settings.cache_clear()
