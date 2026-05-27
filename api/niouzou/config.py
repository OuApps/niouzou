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
    miniflux_api_key: str
    jwt_secret: str = "change-me"  # required for the API; cron jobs don't use it

    # --- JWT (sensible defaults) ---
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # --- Optional (sensible defaults) ---
    openrouter_api_key: str | None = None
    openrouter_model: str = "mistralai/mistral-small"
    score_threshold: float = 0.0
    random_surface_rate: float = 0.05
    feed_gravity: float = 1.5
    cron_fetch_interval: int = 15
    cron_enrich_interval: int = 30

    # Max entries pulled from Miniflux per cron_fetch run.
    miniflux_fetch_batch_size: int = 100

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
