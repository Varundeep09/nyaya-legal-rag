"""
User feedback endpoint for Nyaya Legal Assistant.
Stores user ratings and comments on chat responses in PostgreSQL.
"""

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.models import Feedback
from app.core.logging import logger

router = APIRouter(tags=["Feedback"])


class FeedbackCreateRequest(BaseModel):
    message_id: Optional[str] = None
    session_id: str = Field(..., description="Unique chat session ID")
    rating: str = Field(..., description="Feedback rating ('up' or 'down')")
    comment: Optional[str] = Field(None, description="Optional user comment")


class FeedbackResponse(BaseModel):
    id: str
    session_id: str
    rating: str
    comment: Optional[str]
    status: str = "recorded"


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(request: FeedbackCreateRequest):
    """
    Submit user feedback on a legal assistant response.
    Validates rating ('up' or 'down') and persists to PostgreSQL feedback table.
    """
    clean_rating = request.rating.strip().lower()
    if clean_rating not in ["up", "down"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rating must be either 'up' or 'down'."
        )

    parsed_msg_id = None
    if request.message_id:
        try:
            parsed_msg_id = uuid.UUID(request.message_id)
        except ValueError:
            # If client sends a non-UUID message_id, leave it as None or generate UUID
            parsed_msg_id = None

    feedback_row = Feedback(
        id=uuid.uuid4(),
        message_id=parsed_msg_id,
        session_id=request.session_id,
        rating=clean_rating,
        comment=request.comment.strip() if request.comment else None,
    )

    try:
        async with AsyncSessionLocal() as db_session:
            db_session.add(feedback_row)
            await db_session.commit()
            await db_session.refresh(feedback_row)
    except Exception as e:
        logger.error(f"Failed to record user feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback in database."
        )

    logger.info(f"Recorded feedback {feedback_row.id} ({feedback_row.rating}) for session '{feedback_row.session_id}'")

    return FeedbackResponse(
        id=str(feedback_row.id),
        session_id=feedback_row.session_id,
        rating=feedback_row.rating,
        comment=feedback_row.comment,
        status="recorded"
    )
