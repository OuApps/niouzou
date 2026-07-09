"""Application settings, sourced exclusively from environment variables.

Per project conventions, this is the only place env vars are read — never
call os.environ directly elsewhere.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
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
    openrouter_model: str = "google/gemma-4-26b-a4b-it:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Per-request timeout for OpenRouter calls; free models can be slow.
    openrouter_timeout: float = 60.0
    # E21-S1 — OpenRouter model for the article chat (conversation wants a
    # dialogue/reasoning model; enrichment wants cheap + fast). None → falls
    # back to the effective openrouter_model so existing instances keep
    # working without touching their config. Admin-overridable via
    # app_settings like the rest.
    chat_model: str | None = None
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
    # Pipe-separated (|||) extra boilerplate signatures (E10-S6), merged with
    # the built-in EBRA/cookie-wall lists in enrichment_service.py. Lets an
    # operator add a new paywall/CGU signature without a code change when one
    # slips through. `_exact` = full normalized-text match (near-zero false
    # positives). `_markers` = groups of substrings that must ALL co-occur —
    # avoid generic RGPD/cookies vocabulary that could appear in a legitimate
    # article about that topic; prefer source-specific strings (emails,
    # CMS-only phrasings). Groups within `_markers` are separated by `|||`,
    # substrings within a group by `&&`.
    enrichment_boilerplate_exact: str = ""
    enrichment_boilerplate_markers: str = ""
    # Char cap on the combined LLM enrichment input (header + vocab + title +
    # article excerpt). The lede + first paragraphs carry the topic; sending
    # more inflates latency/cost on slow models. Raising it gives the model
    # more real text to ground its summary on (fewer hallucinations) at the
    # cost of more tokens per article. Admin-overridable via app_settings.
    enrichment_input_max_chars: int = 2500
    cron_fetch_interval: int = 15
    cron_enrich_interval: int = 30
    # UTC hour for the nightly refresh: keyword-weight recompute + rescore of
    # both scores within the window (E8-S6, renamed in E16-S9). The legacy
    # CRON_REFRESH_WEIGHTS_HOUR env var is still honoured as a fallback so a
    # deployment can migrate its config at its own pace.
    cron_nightly_refresh_hour: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "cron_nightly_refresh_hour", "cron_refresh_weights_hour"
        ),
    )

    # --- Smart Match (E16) ---
    # Active score selector (E16-S9): 'keyword' (AI keywords × weights, the
    # default) or 'smart' (embedding k-NN). Both scores are always computed;
    # this only picks which one drives the feed filter + ranking. 'classic'
    # is accepted as a legacy alias of 'keyword'. Admin-overridable via
    # app_settings like the rest.
    scoring_mode: str = "keyword"
    # k-NN neighbourhood size per polarity (liked / disliked).
    smart_topk: int = 5
    # Weight of the dislike term: raw = S+ − λ·S−.
    smart_lambda: float = 0.8
    # Sigmoid steepness on the raw k-NN signal. The raw signal (S+ − λ·S−)
    # is small in magnitude on real article embeddings (cosines cluster in a
    # narrow band), so a gentle β squashes every score onto ~0.5 — a measured
    # prod distribution had median 0.509 / p90 0.572 / max 0.774, i.e. a 0.70
    # threshold matched almost nothing. β=2.0 stretches the sigmoid so genuine
    # matches reach 0.8–1.0 and a threshold becomes selective again.
    smart_beta: float = 2.0
    # Feedback decay half-life: a like this old counts half (0.5^(age/halflife)).
    smart_decay_halflife_days: int = 90
    # Nightly rescoring window — only articles ingested within the last N days
    # get their relevance score recomputed in smart mode (E16-S3).
    smart_rescore_window_days: int = 14
    # Hard cap on the PyTorch/OpenMP thread pool used by the embedding model
    # (E16). Containers (Railway) expose the *host* core count to torch
    # (os.cpu_count → 48) while the cgroup quota is a handful of vCPU, so torch
    # spins up far more threads than it has CPU time for — measured ~180×
    # slowdown (142s vs 0.8s/embed at 48 vs 8 threads). None → auto-detect the
    # cgroup CPU quota, capped low (4 threads already matches 8 in throughput
    # — 0.70s vs 0.79s — so more only burns vCPU-seconds for no speed-up). Set
    # explicitly to override (e.g. EMBEDDING_NUM_THREADS=3 to trim the bill).
    embedding_num_threads: int | None = None

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
