"""Service account key lifecycle (E22-S2).

Generation / listing / revocation for the admin panel, plus ``authenticate``
which the MCP endpoint uses to turn an ``Authorization: Bearer nzk_…`` header
into the owning ``User``. The raw token exists only in memory at creation
time — everything persisted is the SHA-256 fingerprint.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from niouzou.deps import SessionDep
from niouzou.errors import not_found
from niouzou.models import ServiceAccountKey, User
from niouzou.security import (
    api_key_prefix,
    generate_api_key,
    hash_api_key,
)


class ServiceAccountService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def create(
        self, owner_id: uuid.UUID, name: str
    ) -> tuple[ServiceAccountKey, str]:
        """Mint a key for ``owner_id``. Returns the row and the raw token.

        The token is shown to the admin exactly once — only its hash is
        stored, so it can never be recovered afterwards.
        """
        raw_token = generate_api_key()
        key = ServiceAccountKey(
            user_id=owner_id,
            name=name,
            prefix=api_key_prefix(raw_token),
            key_hash=hash_api_key(raw_token),
        )
        self.session.add(key)
        await self.session.flush()
        # ``created_at`` is a server-side default — refresh so the create
        # response carries a real timestamp rather than a None the schema
        # can't validate.
        await self.session.refresh(key)
        return key, raw_token

    async def list_all(self) -> list[ServiceAccountKey]:
        """Every key, newest first — the admin panel shows revoked ones too."""
        return list(
            await self.session.scalars(
                select(ServiceAccountKey).order_by(
                    ServiceAccountKey.created_at.desc()
                )
            )
        )

    async def revoke(self, key_id: uuid.UUID) -> None:
        """Soft-revoke a key. 404 if unknown; a no-op if already revoked."""
        key = await self.session.get(ServiceAccountKey, key_id)
        if key is None:
            raise not_found("Service account key not found")
        if key.revoked_at is None:
            key.revoked_at = datetime.now(timezone.utc)

    async def authenticate(self, raw_token: str) -> User | None:
        """Resolve a raw token to its owner, or ``None`` if it's not valid.

        Matches on the hash, refuses revoked keys, and stamps ``last_used_at``
        so the admin can spot dormant keys. The write rides the request's
        session commit like any other handler mutation.
        """
        if not raw_token:
            return None
        key = await self.session.scalar(
            select(ServiceAccountKey).where(
                ServiceAccountKey.key_hash == hash_api_key(raw_token),
                ServiceAccountKey.revoked_at.is_(None),
            )
        )
        if key is None:
            return None
        key.last_used_at = datetime.now(timezone.utc)
        return await self.session.get(User, key.user_id)
