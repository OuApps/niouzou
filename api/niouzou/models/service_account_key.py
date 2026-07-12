"""Service account API keys for the MCP server (E22-S1).

A key lets a machine client (Claude Desktop, an agent, an IDE…) reach the MCP
endpoint on behalf of the user who created it — same sources, same scores as
that user's REST feed. The raw token is never stored: we keep its SHA-256
(``key_hash``) plus a short display ``prefix`` so the admin can tell keys apart
in the UI. Revocation is soft (``revoked_at``) so the row survives for audit.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from niouzou.db import Base


class ServiceAccountKey(Base):
    __tablename__ = "service_account_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    # The user whose context the key borrows (the creating admin). ON DELETE
    # CASCADE via the FK so deleting a user takes their keys with them.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # ``nzk_`` + first 8 base64url chars of the raw token — display only.
    prefix: Mapped[str] = mapped_column(String, nullable=False)
    # SHA-256 hex of the raw token. Unique so a (theoretical) collision surfaces
    # as an integrity error rather than a silent auth mix-up.
    key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
