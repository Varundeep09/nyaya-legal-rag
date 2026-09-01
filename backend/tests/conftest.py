import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import settings  # noqa: E402


@pytest_asyncio.fixture
async def test_session():
    """
    Yields an AsyncSession backed by a NullPool engine so asyncpg connections
    are cleanly closed and never leak across event loops between tests.
    """
    engine = create_async_engine(
        settings.async_database_url, poolclass=NullPool, future=True
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session

    await engine.dispose()
