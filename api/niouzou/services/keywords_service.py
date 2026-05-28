"""Keyword-weight business logic (GET /keywords, PATCH /keywords/{term})."""

import uuid

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from niouzou.deps import SessionDep
from niouzou.errors import not_found
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

    async def patch_keyword(
        self,
        user_id: uuid.UUID,
        term: str,
        weight: float | None,
        manually_overridden: bool | None,
    ) -> KeywordOut:
        """Update weight and/or the manual-override pin for a keyword.

        - ``weight`` set: pin the weight (default ``manually_overridden=True``).
        - ``manually_overridden=False`` alone: clear the pin, keep the weight.
        - When both fields are None, this is a no-op that still returns the row.
        """
        if weight is not None:
            # Default to pinning unless the caller explicitly opts out.
            pin = True if manually_overridden is None else manually_overridden
            stmt = (
                pg_insert(KeywordWeight)
                .values(
                    user_id=user_id,
                    term=term,
                    weight=weight,
                    manually_overridden=pin,
                )
                .on_conflict_do_update(
                    index_elements=["user_id", "term"],
                    set_={
                        "weight": weight,
                        "manually_overridden": pin,
                        "updated_at": func.now(),
                    },
                )
                .returning(KeywordWeight)
            )
            row = (await self.session.execute(stmt)).scalar_one()
            return KeywordOut.model_validate(row)

        # No weight: must be a pin-only update or no-op.
        existing = await self.session.scalar(
            select(KeywordWeight).where(
                KeywordWeight.user_id == user_id, KeywordWeight.term == term
            )
        )
        if existing is None:
            raise not_found("Keyword not found")

        if manually_overridden is not None:
            stmt = (
                update(KeywordWeight)
                .where(
                    KeywordWeight.user_id == user_id, KeywordWeight.term == term
                )
                .values(manually_overridden=manually_overridden, updated_at=func.now())
                .returning(KeywordWeight)
            )
            row = (await self.session.execute(stmt)).scalar_one()
            return KeywordOut.model_validate(row)

        return KeywordOut.model_validate(existing)

    async def reset_all(self, user_id: uuid.UUID) -> None:
        """Hard-delete every keyword_weight row for this user (E7-S13)."""
        await self.session.execute(
            delete(KeywordWeight).where(KeywordWeight.user_id == user_id)
        )


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(limit, _MAX_LIMIT))
