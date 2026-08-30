"""
Async pytest tests for real PostgreSQL database operations and pgvector operations.
"""

import uuid
import random
import pytest
from sqlalchemy import select

from app.core.db import AsyncSessionLocal, init_db
from app.core.models import StatuteChunk


@pytest.mark.asyncio
async def test_statute_chunk_crud_with_vector():
    """Tests inserting, querying with vector, asserting, and deleting a StatuteChunk row."""
    # Ensure tables and extension exist
    await init_db()

    async with AsyncSessionLocal() as session:
        # Generate a dummy 768-dimensional float vector for bge-base-en-v1.5 embedding
        dummy_vector = [random.uniform(-1.0, 1.0) for _ in range(768)]
        unique_chunk_id = f"test-bns-s103-{uuid.uuid4().hex[:8]}"
        expected_text = "Whoever commits murder shall be punished with death or imprisonment for life."

        # 1. Insert dummy StatuteChunk row
        chunk = StatuteChunk(
            act="Bharatiya Nagarik Suraksha Sanhita, 2023",
            act_short="BNSS",
            chapter="V",
            chapter_title="Arrest of Persons",
            section_number="35",
            section_title="When police may arrest without warrant",
            subsection="(1)",
            clause="a",
            text=expected_text,
            has_illustration=False,
            has_proviso=True,
            has_exception=False,
            page_start=13,
            page_end=13,
            chunk_id=unique_chunk_id,
            source_uri="f:/Dhron AI/Assignment/BNS bare act 2023.pdf",
            references_json=["section 35(3)"],
            embedding=dummy_vector
        )

        session.add(chunk)
        await session.commit()

        # 2. Query back by chunk_id
        stmt = select(StatuteChunk).where(StatuteChunk.chunk_id == unique_chunk_id)
        result = await session.execute(stmt)
        queried_chunk = result.scalar_one_or_none()

        assert queried_chunk is not None
        assert queried_chunk.chunk_id == unique_chunk_id
        assert queried_chunk.text == expected_text
        assert queried_chunk.embedding is not None
        assert len(queried_chunk.embedding) == 768

        # 3. Clean up (delete the row)
        await session.delete(queried_chunk)
        await session.commit()

        # 4. Verify deletion
        result_deleted = await session.execute(stmt)
        assert result_deleted.scalar_one_or_none() is None
