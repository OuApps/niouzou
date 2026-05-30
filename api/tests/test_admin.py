"""Admin endpoints (E8) — settings persistence, config endpoints, users."""

import pytest

from niouzou.errors import APIError
from niouzou.services.auth_service import AuthService
from niouzou.services.settings_service import (
    SettingsService,
    UnknownSettingError,
    mask_api_key,
)


def test_mask_api_key():
    assert mask_api_key(None) is None
    assert mask_api_key("") is None
    assert mask_api_key("sk-abcdefghij") == "sk-...ghij"
    assert mask_api_key("short") == "***"


async def test_settings_get_falls_back_to_env_defaults(db_session):
    svc = SettingsService(db_session)
    # No DB row → returns the value from the env-backed Settings.
    assert await svc.get("openrouter_model") == "nvidia/nemotron-3-super-120b-a12b:free"
    assert await svc.get("max_keywords_per_article") == 6
    assert await svc.get("cron_fetch_interval") == 15
    assert await svc.get("cron_refresh_weights_hour") == 3


async def test_settings_set_then_get_returns_typed_override(db_session):
    svc = SettingsService(db_session)
    await svc.set("openrouter_model", "openai/gpt-4o")
    await svc.set("max_keywords_per_article", 10)
    await db_session.commit()

    assert await svc.get("openrouter_model") == "openai/gpt-4o"
    # Stored as TEXT but typed back as int per INT_KEYS.
    assert await svc.get("max_keywords_per_article") == 10


async def test_settings_set_rejects_unknown_key(db_session):
    svc = SettingsService(db_session)
    with pytest.raises(UnknownSettingError):
        await svc.set("rogue_key", "value")


async def test_settings_empty_string_clears_override(db_session):
    svc = SettingsService(db_session)
    await svc.set("openrouter_api_key", "sk-real-key")
    await db_session.commit()
    assert await svc.get("openrouter_api_key") == "sk-real-key"

    # Empty string means "fall back to env" — DB row is removed.
    await svc.set("openrouter_api_key", "")
    await db_session.commit()
    # env var is None for openrouter_api_key in tests.
    assert await svc.get("openrouter_api_key") is None


async def test_settings_get_effective_snapshots_all_keys(db_session):
    svc = SettingsService(db_session)
    await svc.set("openrouter_model", "openai/gpt-4o")
    await svc.set("cron_refresh_weights_hour", 7)
    await db_session.commit()

    cfg = await svc.get_effective()
    assert cfg.openrouter_model == "openai/gpt-4o"
    assert cfg.cron_refresh_weights_hour == 7
    # Untouched keys come from env defaults.
    assert cfg.max_keywords_per_article == 6


async def test_first_registered_user_is_admin(db_session):
    svc = AuthService(db_session)
    await svc.register("alice@test.dev", "securepassword")
    await db_session.commit()
    await svc.register("bob@test.dev", "securepassword")
    await db_session.commit()

    from sqlalchemy import select

    from niouzou.models import User

    alice = await db_session.scalar(select(User).where(User.email == "alice@test.dev"))
    bob = await db_session.scalar(select(User).where(User.email == "bob@test.dev"))
    assert alice.is_admin is True
    assert bob.is_admin is False


async def test_require_admin_blocks_non_admin():
    """get_current_admin raises 403 for non-admin users."""
    import uuid

    from niouzou.deps import get_current_admin
    from niouzou.models import User

    user = User(
        id=uuid.uuid4(),
        email="x@test.dev",
        password_hash="x",
        is_admin=False,
    )
    with pytest.raises(APIError) as exc:
        await get_current_admin(user)
    assert exc.value.status_code == 403

    user.is_admin = True
    # Admin path returns the same user unchanged.
    assert (await get_current_admin(user)) is user
