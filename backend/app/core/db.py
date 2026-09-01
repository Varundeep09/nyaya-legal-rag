"""
Async database engine, session management, and extension/table initialization for Nyaya.
"""

from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import logger
from app.core.models import Base

# Create Async SQLAlchemy Engine with NullPool for robust multi-loop & async worker execution
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    future=True,
    poolclass=NullPool,
)


# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initializes PostgreSQL database by ensuring the pgvector extension exists
    and creating declarative tables.

    NOTE ON MIGRATIONS:
    Using `run_sync(Base.metadata.create_all)` is a deliberate time-saving choice
    for the assignment timeline. In a production system post-assignment, a formal
    Alembic migration setup (`alembic revision --autogenerate`) would replace this.
    """
    logger.info("Initializing database and pgvector extension...")
    async with engine.begin() as conn:
        # 1. Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        logger.info("Executed: CREATE EXTENSION IF NOT EXISTS vector;")

        # 2. Create declarative tables (temporary run_sync approach for assignment)
        await conn.run_sync(Base.metadata.create_all)
        logger.info(
            "All database tables created successfully via Base.metadata.create_all."
        )
