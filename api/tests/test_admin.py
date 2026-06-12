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
    assert await svc.get("cron_nightly_refresh_hour") == 3


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
    await svc.set("cron_nightly_refresh_hour", 7)
    await db_session.commit()

    cfg = await svc.get_effective()
    assert cfg.openrouter_model == "openai/gpt-4o"
    assert cfg.cron_nightly_refresh_hour == 7
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


# ── E16-S4/S9 — scoring_mode selector ─────────────────────────────────────────


async def test_scoring_mode_defaults_to_keyword(db_session):
    svc = SettingsService(db_session)
    assert await svc.get("scoring_mode") == "keyword"
    cfg = await svc.get_effective()
    assert cfg.scoring_mode == "keyword"
    # Smart knobs resolve to their documented defaults.
    assert cfg.smart_topk == 5
    assert cfg.smart_lambda == 0.8
    assert cfg.smart_beta == 2.0
    assert cfg.smart_decay_halflife_days == 90
    assert cfg.smart_rescore_window_days == 14


async def test_scoring_mode_legacy_classic_normalises_to_keyword(db_session):
    """Pre-E16-S9 deployments may still carry 'classic' (env var or stale DB
    row) — reads collapse it onto the new whitelist."""
    svc = SettingsService(db_session)
    await svc.set("scoring_mode", "classic")
    await db_session.commit()
    assert await svc.get("scoring_mode") == "keyword"
    assert (await svc.get_effective()).scoring_mode == "keyword"


async def test_validate_rejects_unknown_scoring_mode_value(db_session):
    from niouzou.services.settings_service import InvalidSettingError

    svc = SettingsService(db_session)
    with pytest.raises(InvalidSettingError, match="keyword"):
        await svc.validate("scoring_mode", "bogus")


async def test_validate_smart_refused_without_embedding_lib(db_session, monkeypatch):
    from niouzou.services import settings_service as ss
    from niouzou.services.settings_service import InvalidSettingError

    monkeypatch.setattr(ss, "embedding_available", lambda: False)
    svc = SettingsService(db_session)
    with pytest.raises(InvalidSettingError, match="embeddings"):
        await svc.validate("scoring_mode", "smart")
    # keyword is always accepted, lib or not.
    await svc.validate("scoring_mode", "keyword")


async def test_validate_smart_ok_with_lib_and_pgvector(db_session, monkeypatch):
    from niouzou.services import settings_service as ss

    # The test DB runs pgvector/pgvector:pg17 with the extension installed,
    # so faking the lib presence is enough for the happy path.
    monkeypatch.setattr(ss, "embedding_available", lambda: True)
    svc = SettingsService(db_session)
    await svc.validate("scoring_mode", "smart")  # must not raise

    await svc.set("scoring_mode", "smart")
    await db_session.commit()
    assert await svc.get("scoring_mode") == "smart"


async def test_validate_ignores_other_keys(db_session):
    svc = SettingsService(db_session)
    # No environment checks for non-scoring_mode keys.
    await svc.validate("openrouter_model", "openai/gpt-4o")
    await svc.validate("smart_topk", 7)


async def test_embedding_counts(db_session):
    from niouzou.services.stats_service import embedding_counts
    from tests.factories import make_article, make_source, make_user
    from tests.fake_embeddings import axis_vector

    user = await make_user(db_session)
    source = await make_source(db_session, user)
    embedded = await make_article(db_session, source, title="with")
    embedded.embedding = axis_vector(0)
    await make_article(db_session, source, title="without")
    await db_session.flush()

    assert await embedding_counts(db_session) == (1, 2)


async def test_me_exposes_scoring_mode(db_session):
    from niouzou.services.me_service import MeService
    from tests.factories import make_user

    user = await make_user(db_session)
    me = await MeService(db_session).get(user.id)
    assert me.scoring_mode == "keyword"

    await SettingsService(db_session).set("scoring_mode", "smart")
    me = await MeService(db_session).get(user.id)
    assert me.scoring_mode == "smart"
