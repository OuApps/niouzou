"""Current-user profile schema (GET /me, E7-S9)."""

from pydantic import BaseModel, EmailStr


class Me(BaseModel):
    email: EmailStr
    is_admin: bool
    saved_count: int
    keyword_count: int
    source_count: int
    # E16-S5 — active scoring engine ('classic' | 'smart'), read-only. Lets
    # the Keywords screen show the Smart Match banner without an admin call.
    scoring_mode: str
