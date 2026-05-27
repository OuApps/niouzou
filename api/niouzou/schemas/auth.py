"""Auth request/response schemas (POST /auth/register|login|refresh)."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    """Returned by register and login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    """Returned by refresh — a fresh access token only."""

    access_token: str
    token_type: str = "bearer"
