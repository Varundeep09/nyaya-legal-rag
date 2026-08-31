"""
Pytest configuration and shared fixtures for Nyaya tests.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


@pytest_asyncio.fixture
async def test_session():
    """
    Yields an AsyncSession backed by a NullPool engine so asyncpg connections
    are cleanly closed and never leak across event loops between tests.
    """
    engine = create_async_engine(
        settings.async_database_url,
        poolclass=NullPool,
        future=True
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()
