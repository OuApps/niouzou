"""Admin config + models schemas (E8-S3)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminConfig(BaseModel):
    """Effective values for every overridable setting.

    ``openrouter_api_key`` is masked (``sk-...a3f9``) on every read — the
    plaintext value never leaves the API.
    """

    openrouter_model: str
    openrouter_api_key: str | None
    max_keywords_per_article: int
    cron_fetch_interval: int
    cron_refresh_weights_hour: int
    score_threshold: float
    # E16-S4 — scoring engine ('classic' | 'smart') + instance-wide embedding
    # coverage so the admin can judge whether a backfill is worth running
    # before switching to Smart Match.
    scoring_mode: str
    embeddings_done: int
    articles_total: int


class AdminConfigPatch(BaseModel):
    """Partial update for ``PATCH /admin/config``.

    Every field is optional; omitted fields are left untouched. An empty
    string on ``openrouter_api_key`` deletes the DB override and falls back
    to the env var.
    """

    openrouter_model: str | None = None
    openrouter_api_key: str | None = None
    max_keywords_per_article: int | None = Field(default=None, ge=1, le=50)
    cron_fetch_interval: int | None = Field(default=None, ge=1, le=1440)
    cron_refresh_weights_hour: int | None = Field(default=None, ge=0, le=23)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    # Value-validated in SettingsService.validate (422 when 'smart' is not
    # runnable on this instance), not by the schema.
    scoring_mode: str | None = None


class AdminModel(BaseModel):
    """OpenRouter model curated for the admin selector (GET /admin/models)."""

    id: str
    name: str
    input_price_per_m: float
    output_price_per_m: float
    context_length: int


class AdminUser(BaseModel):
    """Single row in GET /admin/users (E8-S5)."""

    id: str
    email: str
    is_admin: bool
    created_at: datetime


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


# ── E10-S3 — Keyword compaction ───────────────────────────────────────────


class CompactionGroup(BaseModel):
    """One proposed merge: ``aliases`` will be rewritten as ``canonical``.

    ``skipped_reason`` is annotated server-side at apply time on groups
    touching a ``manually_overridden=true`` term — those are returned as
    informational rows but not applied (the user's explicit pin wins).
    """

    canonical: str
    aliases: list[str]
    skipped_reason: str | None = None


class CompactionPreview(BaseModel):
    """Response body of ``POST /admin/compact-keywords/preview``."""

    id: str
    groups: list[CompactionGroup]


class CompactionApplyRequest(BaseModel):
    id: str


class LlmPromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    body: str
    updated_at: datetime


class LlmPromptUpdate(BaseModel):
    body: str = Field(..., min_length=1)
