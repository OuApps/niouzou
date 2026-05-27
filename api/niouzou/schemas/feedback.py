"""Feedback schemas (POST /feedback)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

FeedbackAction = Literal["like", "dislike", "skip", "save"]


class FeedbackRequest(BaseModel):
    article_id: uuid.UUID
    action: FeedbackAction


class FeedbackResponse(BaseModel):
    article_id: uuid.UUID
    action: FeedbackAction
    updated_at: datetime
