"""Runtime-overridable settings (E8-S2).

Some env-var-backed settings (``OPENROUTER_MODEL``, ``OPENROUTER_API_KEY``,
``MAX_KEYWORDS_PER_ARTICLE``, ``CRON_FETCH_INTERVAL``,
``CRON_NIGHTLY_REFRESH_HOUR``) must be tunable by the admin without a
redeploy. ``SettingsService`` persists overrides in ``app_settings`` and
resolves the effective value at read time:

    effective = DB override (if present) else env var (via ``config.Settings``)

Env vars therefore stay the source of truth on fresh installs; the DB only
holds drift the admin introduced through the UI.

Two of the keys — ``CRON_FETCH_INTERVAL`` and ``CRON_NIGHTLY_REFRESH_HOUR`` —
are read by the refresh worker at startup only; persisted changes take effect
on the next worker restart (APScheduler triggers are not rebuilt live).
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from niouzou.config import get_settings
from niouzou.deps import SessionDep
from niouzou.models import AppSetting
from niouzou.services.embedding_service import embedding_available

# Public registry of keys an admin may override at runtime.
OVERRIDABLE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "openrouter_api_key",
        "openrouter_model",
        # E21-S1 — dedicated model for the article chat; empty/unset falls
        # back to openrouter_model (see ``get`` / ``get_effective``).
        "chat_model",
        # E21-S7 — enable OpenRouter's web plugin on chat completions so the
        # assistant can search the internet (works with any model).
        "chat_web_search",
        "max_keywords_per_article",
        "cron_fetch_interval",
        "cron_nightly_refresh_hour",
        "score_threshold",
        "random_surface_rate",
        "enrichment_input_max_chars",
        # E16 — Smart Match engine + its tuning knobs.
        "scoring_mode",
        "smart_topk",
        "smart_lambda",
        "smart_beta",
        "smart_decay_halflife_days",
        "smart_rescore_window_days",
    }
)

# Keys whose raw value must never leave the API in plaintext.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset({"openrouter_api_key"})

# Keys parsed as integers (the ``app_settings.value`` column is TEXT).
INT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "max_keywords_per_article",
        "cron_fetch_interval",
        "cron_nightly_refresh_hour",
        "enrichment_input_max_chars",
        "smart_topk",
        "smart_decay_halflife_days",
        "smart_rescore_window_days",
    }
)

# Keys parsed as floats — same TEXT column, different cast on read/write.
FLOAT_KEYS: Final[frozenset[str]] = frozenset(
    {"score_threshold", "random_surface_rate", "smart_lambda", "smart_beta"}
)

# Keys parsed as booleans — stored as "true"/"false" in the TEXT column.
BOOL_KEYS: Final[frozenset[str]] = frozenset({"chat_web_search"})


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("true", "1", "yes", "on")

# Env-default lookups: SettingsService.get(key) falls back to these when no DB
# override exists. Kept as a small registry so ``GET /admin/config`` can show
# the user the same values the rest of the app would observe.
_DEFAULT_FROM_SETTINGS = {
    "openrouter_api_key": lambda s: s.openrouter_api_key,
    "openrouter_model": lambda s: s.openrouter_model,
    # May be None — the fallback onto the effective openrouter_model happens
    # in ``get`` / ``get_effective`` so a DB-overridden enrichment model is
    # honoured too (env-level fallback alone would miss it).
    "chat_model": lambda s: s.chat_model,
    "chat_web_search": lambda s: s.chat_web_search,
    "max_keywords_per_article": lambda s: s.max_keywords_per_article,
    "cron_fetch_interval": lambda s: s.cron_fetch_interval,
    "cron_nightly_refresh_hour": lambda s: s.cron_nightly_refresh_hour,
    "score_threshold": lambda s: s.score_threshold,
    "random_surface_rate": lambda s: s.random_surface_rate,
    "enrichment_input_max_chars": lambda s: s.enrichment_input_max_chars,
    "scoring_mode": lambda s: s.scoring_mode,
    "smart_topk": lambda s: s.smart_topk,
    "smart_lambda": lambda s: s.smart_lambda,
    "smart_beta": lambda s: s.smart_beta,
    "smart_decay_halflife_days": lambda s: s.smart_decay_halflife_days,
    "smart_rescore_window_days": lambda s: s.smart_rescore_window_days,
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
    cron_nightly_refresh_hour: int
    score_threshold: float
    # Defaulted so existing call sites (and tests) that build the snapshot by
    # hand keep working; get_effective() always fills them in.
    random_surface_rate: float = 0.05
    # E21-S1 — get_effective() resolves the fallback chain (DB override →
    # env CHAT_MODEL → effective openrouter_model), so consumers read this
    # field directly. The default only serves hand-built snapshots.
    chat_model: str = "openrouter/auto"
    # E21-S7 — when true, chat completions carry OpenRouter's web plugin.
    chat_web_search: bool = False
    enrichment_input_max_chars: int = 2500
    # E16 — defaulted so existing call sites (and tests) that build the
    # snapshot by hand keep working; get_effective() always fills them in.
    scoring_mode: str = "keyword"
    smart_topk: int = 5
    smart_lambda: float = 0.8
    smart_beta: float = 2.0
    smart_decay_halflife_days: int = 90
    smart_rescore_window_days: int = 14


def normalize_scoring_mode(value: object) -> str:
    """Collapse the stored/env value onto the E16-S9 whitelist.

    ``'classic'`` survives as a legacy alias of ``'keyword'`` (pre-S9 env
    vars or DB rows); anything unknown falls back to ``'keyword'`` so the
    feed never breaks on a typo'd env var.
    """
    return "smart" if value == "smart" else "keyword"


def mask_api_key(value: str | None) -> str | None:
    """``sk-...a3f9`` style mask for API keys returned to the admin UI."""
    if not value:
        return None
    if len(value) <= 7:
        return "***"
    return f"{value[:3]}...{value[-4:]}"


class UnknownSettingError(KeyError):
    """Raised when a caller asks for a key not in ``OVERRIDABLE_KEYS``."""


class InvalidSettingError(ValueError):
    """Raised when a value fails admin-facing validation; maps to 422."""


class SettingsService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    @staticmethod
    def _env_default(key: str) -> str | int | None:
        if key not in _DEFAULT_FROM_SETTINGS:
            raise UnknownSettingError(key)
        return _DEFAULT_FROM_SETTINGS[key](get_settings())

    async def get(self, key: str) -> str | int | float | None:
        """Effective value for ``key``: DB override or env fallback.

        Returns the value typed per ``INT_KEYS`` / ``FLOAT_KEYS`` — strings
        stay strings, integers come back as ``int``, floats as ``float``.
        Raises ``UnknownSettingError`` for unknown keys so the admin endpoints
        can return 400 cleanly.
        """
        if key not in OVERRIDABLE_KEYS:
            raise UnknownSettingError(key)
        override = await self.session.scalar(
            select(AppSetting.value).where(AppSetting.key == key)
        )
        if override is None:
            default = self._env_default(key)
            if key == "chat_model" and not default:
                # E21-S1 — unset chat model falls back to the *effective*
                # enrichment model (DB override included), not just the env.
                return await self.get("openrouter_model")
            return default
        if key in INT_KEYS:
            return int(override)
        if key in FLOAT_KEYS:
            return float(override)
        if key in BOOL_KEYS:
            return _parse_bool(override)
        if key == "scoring_mode":
            return normalize_scoring_mode(override)
        return override

    async def validate(self, key: str, value: str | int | float | None) -> None:
        """Admin-facing validation, called by ``PATCH /admin/config`` before
        ``set`` (E16-S4). Kept separate from ``set`` so internal callers
        (tests, scripts) aren't blocked by environment checks.

        ``scoring_mode = 'smart'`` is refused unless the optional
        sentence-transformers dependency is installed AND the pgvector
        extension exists in the database — flipping the switch on an
        instance that can't embed would silently freeze all scoring at the
        Classic fallback.
        """
        if key != "scoring_mode" or value is None or value == "":
            return
        # 'classic' accepted as a legacy alias of 'keyword' (normalised on
        # read) so older clients / scripts don't break mid-transition.
        if value not in ("keyword", "smart", "classic"):
            raise InvalidSettingError(
                "scoring_mode must be 'keyword' or 'smart'"
            )
        if value == "smart":
            if not embedding_available():
                raise InvalidSettingError(
                    "Smart Match requires the embedding model: install the "
                    "'embeddings' extra (uv sync --extra embeddings) on the "
                    "API/worker image"
                )
            ext = await self.session.scalar(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            if ext is None:
                raise InvalidSettingError(
                    "Smart Match requires the pgvector extension — run the "
                    "database migrations on a pgvector-enabled Postgres "
                    "(pgvector/pgvector:pg17)"
                )

    async def set(self, key: str, value: str | int | float | None) -> None:
        """Upsert an override. ``None`` or empty string deletes the override
        (the next read falls back to the env var)."""
        if key not in OVERRIDABLE_KEYS:
            raise UnknownSettingError(key)
        if value is None or value == "":
            await self.delete(key)
            return
        # Booleans are normalised to "true"/"false" (str(True) would store
        # "True", which reads back fine but keeps the column consistent).
        stored = (
            ("true" if value else "false")
            if key in BOOL_KEYS and isinstance(value, bool)
            else str(value)
        )
        if key in INT_KEYS:
            # Validate now so an admin typo isn't silently persisted.
            int(stored)
        elif key in FLOAT_KEYS:
            float(stored)
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

        def resolve(key: str) -> str | int | float | None:
            raw = db.get(key)
            if raw is None:
                return self._env_default(key)
            if key in INT_KEYS:
                return int(raw)
            if key in FLOAT_KEYS:
                return float(raw)
            if key in BOOL_KEYS:
                return _parse_bool(raw)
            return raw

        return EffectiveConfig(
            openrouter_api_key=resolve("openrouter_api_key"),  # type: ignore[arg-type]
            openrouter_model=resolve("openrouter_model"),  # type: ignore[arg-type]
            # E21-S1 — same fallback chain as ``get``: DB override → env
            # CHAT_MODEL → effective openrouter_model.
            chat_model=resolve("chat_model") or resolve("openrouter_model"),  # type: ignore[arg-type]
            chat_web_search=bool(resolve("chat_web_search")),
            max_keywords_per_article=resolve("max_keywords_per_article"),  # type: ignore[arg-type]
            cron_fetch_interval=resolve("cron_fetch_interval"),  # type: ignore[arg-type]
            cron_nightly_refresh_hour=resolve("cron_nightly_refresh_hour"),  # type: ignore[arg-type]
            score_threshold=resolve("score_threshold"),  # type: ignore[arg-type]
            random_surface_rate=resolve("random_surface_rate"),  # type: ignore[arg-type]
            enrichment_input_max_chars=resolve("enrichment_input_max_chars"),  # type: ignore[arg-type]
            scoring_mode=normalize_scoring_mode(resolve("scoring_mode")),
            smart_topk=resolve("smart_topk"),  # type: ignore[arg-type]
            smart_lambda=resolve("smart_lambda"),  # type: ignore[arg-type]
            smart_beta=resolve("smart_beta"),  # type: ignore[arg-type]
            smart_decay_halflife_days=resolve("smart_decay_halflife_days"),  # type: ignore[arg-type]
            smart_rescore_window_days=resolve("smart_rescore_window_days"),  # type: ignore[arg-type]
        )
