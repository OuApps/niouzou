"""Feedback schemas (POST /feedback)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Reaction = Literal["like", "dislike", "none"]


class FeedbackRequest(BaseModel):
    """Partial-update payload.

    A field set to ``None`` (or omitted) means *do not touch*. ``is_saved``
    accepts both ``True`` and ``False`` (un-save is legal). ``reaction``
    accepts ``"none"`` to clear an existing like/dislike.
    ``read_full_article`` is monotone — only ``True`` is meaningful, the
    backend silently drops ``False``.

    The no-op check (all three fields ``None``) is enforced by the router so
    we return ``400 Bad Request`` rather than Pydantic's auto ``422``.
    """

    article_id: uuid.UUID
    reaction: Reaction | None = None
    is_saved: bool | None = None
    # Literal[True] would refuse `False` at validation time, but we want the
    # silent-drop semantics (and the PWA should never send False here anyway).
    read_full_article: bool | None = None

    def is_no_op(self) -> bool:
        return (
            self.reaction is None
            and self.is_saved is None
            and self.read_full_article is None
        )


class FeedbackState(BaseModel):
    """The persisted feedback state for one (user, article)."""

    reaction: Reaction = "none"
    is_saved: bool = False
    read_full_article: bool = False


class FeedbackResponse(FeedbackState):
    article_id: uuid.UUID
    updated_at: datetime
