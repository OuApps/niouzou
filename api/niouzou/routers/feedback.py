"""Feedback endpoint: POST /feedback."""

from typing import Annotated

from fastapi import APIRouter, Depends

from niouzou.deps import CurrentUser
from niouzou.schemas.feedback import FeedbackRequest, FeedbackResponse
from niouzou.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])

FeedbackServiceDep = Annotated[FeedbackService, Depends()]


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest, user: CurrentUser, service: FeedbackServiceDep
) -> FeedbackResponse:
    return await service.record(user.id, body.article_id, body.action)
