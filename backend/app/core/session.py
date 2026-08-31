"""
Session identity and middleware utilities for Nyaya Legal Assistant.
Ensures session isolation across user uploads and chat histories.
"""

import uuid
from typing import Optional
from fastapi import Request, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ChatSession
from app.core.logging import logger


def get_session_id_from_header(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
) -> str:
    """
    FastAPI dependency extracting session identifier from X-Session-ID header.
    Generates a new UUID4 string if absent or empty.
    """
    if x_session_id and x_session_id.strip():
        return x_session_id.strip()
    return str(uuid.uuid4())


async def ensure_session_exists(session_id: str, db: AsyncSession) -> ChatSession:
    """
    Ensures a ChatSession record exists in PostgreSQL for the given session_id.
    """
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    res = await db.execute(stmt)
    session_obj = res.scalar_one_or_none()

    if not session_obj:
        session_obj = ChatSession(id=session_id)
        db.add(session_obj)
        await db.commit()
        await db.refresh(session_obj)
        logger.info("Created new ChatSession record in DB for session_id '%s'.", session_id)

    return session_obj
