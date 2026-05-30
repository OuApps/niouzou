"""Application settings, sourced exclusively from environment variables.

Per project conventions, this is the only place env vars are read — never
call os.environ directly elsewhere.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Required ---
    database_url: str
    miniflux_url: str
    jwt_secret: str = "change-me"  # required for the API; cron jobs don't use it

    # --- JWT (sensible defaults) ---
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # --- Optional (sensible defaults) ---
    openrouter_api_key: str | None = None
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Per-request timeout for OpenRouter calls; free models can be slow.
    openrouter_timeout: float = 60.0
    score_threshold: float = 0.0
    random_surface_rate: float = 0.05
    feed_gravity: float = 1.5
    # Number of feedbacks below which the feed bypasses SCORE_THRESHOLD entirely
    # (E7-S6). A brand-new user has weight 0 for every keyword, so every score
    # ends up near 0.5 — a positive threshold would yield an empty feed on day
    # one. We open the floodgates until enough signal has been collected.
    cold_start_threshold: int = 10
    # Cap on keywords persisted per article; applied after extraction so it
    # works uniformly for TF-IDF and AI scorers (E7-S5).
    max_keywords_per_article: int = 6
    # Below this content length (chars), an enriched article is flagged as
    # partial / premium (E7-S21). Paywalled feeds typically give a short
    # teaser; full articles are several kilobytes. Tune per deployment.
    premium_content_max_chars: int = 800
    cron_fetch_interval: int = 15
    cron_enrich_interval: int = 30

    # Max entries pulled from Miniflux per cron_fetch run.
    miniflux_fetch_batch_size: int = 100
    # Max pending articles enriched per cron_enrich run.
    enrich_batch_size: int = 50

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise DATABASE_URL to the asyncpg driver SQLAlchemy expects.

        Railway / standard Postgres URLs use the ``postgresql://`` scheme; the
        async engine needs ``postgresql+asyncpg://``.
        """
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
