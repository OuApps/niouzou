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


async def test_delete_user_cascades_to_dependent_rows(db_session):
    """E13-S3 — ``session.delete(user)`` wipes sources, articles and per-row state."""
    from sqlalchemy import func, select

    from niouzou.models import (
        Article,
        ArticleFeedback,
        ArticleRelevanceScore,
        KeywordWeight,
        Source,
        User,
    )
    from tests.factories import make_article, make_source, make_user, set_relevance

    user = await make_user(db_session, email="doomed@test.dev")
    source = await make_source(db_session, user, feed_id=51)
    article = await make_article(db_session, source)
    await set_relevance(db_session, article, user, 0.7)
    db_session.add(
        ArticleFeedback(article_id=article.id, user_id=user.id, reaction="like")
    )
    db_session.add(KeywordWeight(user_id=user.id, term="python", weight=0.8))
    await db_session.commit()

    await db_session.delete(user)
    await db_session.commit()

    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Source)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Article)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(ArticleFeedback))
        == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(ArticleRelevanceScore))
        == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(KeywordWeight)) == 0
    )


async def test_delete_user_refuses_self_deletion(db_session):
    """E13-S3 — admin can't delete their own account (would lock themselves out)."""
    from niouzou.routers.admin import delete_user
    from tests.factories import make_user

    admin = await make_user(db_session, email="admin@test.dev")
    admin.is_admin = True
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await delete_user(user_id=admin.id, admin=admin, session=db_session)
    assert exc.value.status_code == 400


async def test_delete_user_returns_404_on_unknown(db_session):
    import uuid

    from niouzou.routers.admin import delete_user
    from tests.factories import make_user

    admin = await make_user(db_session, email="admin@test.dev")
    admin.is_admin = True
    await db_session.commit()

    with pytest.raises(APIError) as exc:
        await delete_user(user_id=uuid.uuid4(), admin=admin, session=db_session)
    assert exc.value.status_code == 404


async def test_llm_prompts_service_list_get_update(db_session):
    """E13-S2 — list returns rows alphabetically; update mutates body in place."""
    from sqlalchemy import delete

    from niouzou.models import LlmPrompt
    from niouzou.services.llm_prompts_service import LlmPromptsService

    # conftest truncates most tables but llm_prompts is seeded by the migration
    # and shared across tests — wipe it to a known state here.
    await db_session.execute(delete(LlmPrompt))
    db_session.add_all(
        [
            LlmPrompt(name="b.prompt", body="b-body"),
            LlmPrompt(name="a.prompt", body="a-body"),
        ]
    )
    await db_session.commit()

    svc = LlmPromptsService(db_session)
    rows = await svc.list_all()
    assert [r.name for r in rows] == ["a.prompt", "b.prompt"]

    updated = await svc.update("a.prompt", "a-body-v2")
    assert updated.body == "a-body-v2"
    # Round-trip via get.
    assert (await svc.get("a.prompt")).body == "a-body-v2"


async def test_llm_prompts_service_get_unknown_raises_404(db_session):
    from niouzou.errors import APIError as _APIError
    from niouzou.services.llm_prompts_service import LlmPromptsService

    svc = LlmPromptsService(db_session)
    with pytest.raises(_APIError) as exc:
        await svc.get("does.not.exist")
    assert exc.value.status_code == 404


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
