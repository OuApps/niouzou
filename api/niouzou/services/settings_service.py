"""Runtime-overridable settings (E8-S2).

Some env-var-backed settings (``OPENROUTER_MODEL``, ``OPENROUTER_API_KEY``,
``MAX_KEYWORDS_PER_ARTICLE``, ``CRON_FETCH_INTERVAL``,
``CRON_REFRESH_WEIGHTS_HOUR``) must be tunable by the admin without a
redeploy. ``SettingsService`` persists overrides in ``app_settings`` and
resolves the effective value at read time:

    effective = DB override (if present) else env var (via ``config.Settings``)

Env vars therefore stay the source of truth on fresh installs; the DB only
holds drift the admin introduced through the UI.

Two of the keys — ``CRON_FETCH_INTERVAL`` and ``CRON_REFRESH_WEIGHTS_HOUR`` —
are read by the refresh worker at startup only; persisted changes take effect
on the next worker restart (APScheduler triggers are not rebuilt live).
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from niouzou.config import get_settings
from niouzou.models import AppSetting

# Public registry of keys an admin may override at runtime.
OVERRIDABLE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "openrouter_api_key",
        "openrouter_model",
        "max_keywords_per_article",
        "cron_fetch_interval",
        "cron_refresh_weights_hour",
    }
)

# Keys whose raw value must never leave the API in plaintext.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset({"openrouter_api_key"})

# Keys parsed as integers (the ``app_settings.value`` column is TEXT).
INT_KEYS: Final[frozenset[str]] = frozenset(
    {"max_keywords_per_article", "cron_fetch_interval", "cron_refresh_weights_hour"}
)

# Env-default lookups: SettingsService.get(key) falls back to these when no DB
# override exists. Kept as a small registry so ``GET /admin/config`` can show
# the user the same values the rest of the app would observe.
_DEFAULT_FROM_SETTINGS = {
    "openrouter_api_key": lambda s: s.openrouter_api_key,
    "openrouter_model": lambda s: s.openrouter_model,
    "max_keywords_per_article": lambda s: s.max_keywords_per_article,
    "cron_fetch_interval": lambda s: s.cron_fetch_interval,
    # CRON_REFRESH_WEIGHTS_HOUR is new in E8-S6; defaulted here so a fresh
    # install resolves it before the env var lands in pydantic Settings.
    "cron_refresh_weights_hour": lambda s: getattr(
        s, "cron_refresh_weights_hour", 3
    ),
}


@dataclass(slots=True)
class EffectiveConfig:
    """Resolved values for every overridable key, ready to pass into clients.

    Built once per pipeline run so a long enrichment batch sees a consistent
    snapshot even if the admin updates the DB mid-run.
    """

    openrouter_api_key: str | None
    openrouter_model: str
    max_keywords_per_article: int
    cron_fetch_interval: int
    cron_refresh_weights_hour: int


def mask_api_key(value: str | None) -> str | None:
    """``sk-...a3f9`` style mask for API keys returned to the admin UI."""
    if not value:
        return None
    if len(value) <= 7:
        return "***"
    return f"{value[:3]}...{value[-4:]}"


class UnknownSettingError(KeyError):
    """Raised when a caller asks for a key not in ``OVERRIDABLE_KEYS``."""


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _env_default(key: str) -> str | int | None:
        if key not in _DEFAULT_FROM_SETTINGS:
            raise UnknownSettingError(key)
        return _DEFAULT_FROM_SETTINGS[key](get_settings())

    async def get(self, key: str) -> str | int | None:
        """Effective value for ``key``: DB override or env fallback.

        Returns the value typed per ``INT_KEYS`` — strings stay strings,
        integers come back as ``int``. Raises ``UnknownSettingError`` for
        unknown keys so the admin endpoints can return 400 cleanly.
        """
        if key not in OVERRIDABLE_KEYS:
            raise UnknownSettingError(key)
        override = await self.session.scalar(
            select(AppSetting.value).where(AppSetting.key == key)
        )
        if override is None:
            return self._env_default(key)
        return int(override) if key in INT_KEYS else override

    async def set(self, key: str, value: str | int | None) -> None:
        """Upsert an override. ``None`` or empty string deletes the override
        (the next read falls back to the env var)."""
        if key not in OVERRIDABLE_KEYS:
            raise UnknownSettingError(key)
        if value is None or value == "":
            await self.delete(key)
            return
        stored = str(value)
        if key in INT_KEYS:
            # Validate now so an admin typo isn't silently persisted.
            int(stored)
        await self.session.execute(
            pg_insert(AppSetting)
            .values(key=key, value=stored)
            .on_conflict_do_update(
                index_elements=["key"], set_={"value": stored}
            )
        )

    async def delete(self, key: str) -> None:
        if key not in OVERRIDABLE_KEYS:
            raise UnknownSettingError(key)
        await self.session.execute(delete(AppSetting).where(AppSetting.key == key))

    async def get_effective(self) -> EffectiveConfig:
        """Snapshot of every overridable value, typed for downstream use."""
        rows = (
            await self.session.execute(
                select(AppSetting.key, AppSetting.value).where(
                    AppSetting.key.in_(OVERRIDABLE_KEYS)
                )
            )
        ).all()
        db = {k: v for k, v in rows}

        def resolve(key: str) -> str | int | None:
            raw = db.get(key)
            if raw is None:
                return self._env_default(key)
            return int(raw) if key in INT_KEYS else raw

        return EffectiveConfig(
            openrouter_api_key=resolve("openrouter_api_key"),  # type: ignore[arg-type]
            openrouter_model=resolve("openrouter_model"),  # type: ignore[arg-type]
            max_keywords_per_article=resolve("max_keywords_per_article"),  # type: ignore[arg-type]
            cron_fetch_interval=resolve("cron_fetch_interval"),  # type: ignore[arg-type]
            cron_refresh_weights_hour=resolve("cron_refresh_weights_hour"),  # type: ignore[arg-type]
        )
