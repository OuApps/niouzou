"""Current-user profile schema (GET /me, E7-S9)."""

from pydantic import BaseModel, EmailStr


class Me(BaseModel):
    email: EmailStr
    is_admin: bool
    saved_count: int
    keyword_count: int
    source_count: int
