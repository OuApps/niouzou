"""Keyword-weight business logic (GET /keywords, PATCH /keywords/{term})."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from niouzou.deps import SessionDep
from niouzou.models import KeywordWeight
from niouzou.pagination import decode_cursor, encode_cursor
from niouzou.schemas.keywords import KeywordOut, KeywordsResponse

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


class KeywordsService:
    def __init__(self, session: SessionDep) -> None:
        self.session = session

    async def list_keywords(
        self, user_id: uuid.UUID, cursor: str | None, limit: int | None
    ) -> KeywordsResponse:
        page_size = _clamp_limit(limit)
        abs_weight = func.abs(KeywordWeight.weight)

        stmt = (
            select(KeywordWeight)
            .where(KeywordWeight.user_id == user_id)
            .order_by(abs_weight.desc(), KeywordWeight.term.asc())
            .limit(page_size + 1)
        )

        if cursor:
            decoded = decode_cursor(cursor)
            cur_abs = float(decoded["abs"])
            cur_term = str(decoded["term"])
            # Keyset for ORDER BY (abs(weight) DESC, term ASC).
            stmt = stmt.where(
                or_(
                    abs_weight < cur_abs,
                    (abs_weight == cur_abs) & (KeywordWeight.term > cur_term),
                )
            )

        rows = list(await self.session.scalars(stmt))
        has_more = len(rows) > page_size
        rows = rows[:page_size]

        keywords = [KeywordOut.model_validate(r) for r in rows]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(
                {"abs": abs(last.weight), "term": last.term}
            )

        return KeywordsResponse(
            keywords=keywords, next_cursor=next_cursor, has_more=has_more
        )

    async def set_weight(
        self, user_id: uuid.UUID, term: str, weight: float
    ) -> KeywordOut:
        """Manually override a keyword's weight and pin it against recompute."""
        stmt = (
            pg_insert(KeywordWeight)
            .values(
                user_id=user_id,
                term=term,
                weight=weight,
                manually_overridden=True,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "term"],
                set_={
                    "weight": weight,
                    "manually_overridden": True,
                    "updated_at": func.now(),
                },
            )
            .returning(
                KeywordWeight.term,
                KeywordWeight.weight,
                KeywordWeight.like_count,
                KeywordWeight.dislike_count,
                KeywordWeight.updated_at,
            )
        )
        row = (await self.session.execute(stmt)).one()
        return KeywordOut(
            term=row.term,
            weight=row.weight,
            like_count=row.like_count,
            dislike_count=row.dislike_count,
            updated_at=row.updated_at,
        )


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(limit, _MAX_LIMIT))
