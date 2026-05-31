"""Feedback endpoint: POST /feedback."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from niouzou.deps import CurrentUser
from niouzou.schemas.feedback import FeedbackRequest, FeedbackResponse
from niouzou.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])

FeedbackServiceDep = Annotated[FeedbackService, Depends()]


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest, user: CurrentUser, service: FeedbackServiceDep
) -> FeedbackResponse:
    if body.is_no_op():
        # E9-S1 — an empty payload signals a client bug; reject loudly.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of reaction, is_saved, read_full_article must be set",
        )
    return await service.record(user.id, body)
