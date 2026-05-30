"""Current-user profile aggregator (GET /me, E7-S9).

The Profile screen used to compute counts from the first page of each list
endpoint, which underreported the real totals. ``MeService`` returns the
authoritative counts in a single round-trip.
"""

import uuid

from sqlalchemy import func, select

from niouzou.deps import SessionDep
from niouzou.models import ArticleFeedback, KeywordWeight, Source, User
from niouzou.schemas.me import Me


class MeService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> Me:
        user_row = (
            await self.session.execute(
                select(User.email, User.is_admin).where(User.id == user_id)
            )
        ).one()

        saved_count = await self.session.scalar(
            select(func.count())
            .select_from(ArticleFeedback)
            .where(
                ArticleFeedback.user_id == user_id,
                ArticleFeedback.action == "save",
            )
        )

        keyword_count = await self.session.scalar(
            select(func.count())
            .select_from(KeywordWeight)
            .where(KeywordWeight.user_id == user_id)
        )

        source_count = await self.session.scalar(
            select(func.count())
            .select_from(Source)
            .where(
                Source.user_id == user_id,
                Source.deleted_at.is_(None),
            )
        )

        return Me(
            email=user_row.email,
            is_admin=user_row.is_admin,
            saved_count=saved_count or 0,
            keyword_count=keyword_count or 0,
            source_count=source_count or 0,
        )
