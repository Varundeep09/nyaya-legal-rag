"""
Async loader module to ingest narrative BNSS statute chunks into PostgreSQL database.
"""

import os
from typing import Optional, Dict, Any
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import StatuteChunk
from app.core.logging import logger
from app.ingestion.bns_chunker import (
    extract_pages,
    parse_chapters_and_sections,
    DEFAULT_SOURCE_URI,
)


async def load_statute_chunks_to_db(
    session: AsyncSession, pdf_path: str = None, stats: Optional[Dict[str, Any]] = None
) -> int:
    """
    Idempotently ingests narrative BNSS statute chunks (pages 1-157) into PostgreSQL.
    Deletes pre-existing chunks for the same source_uri before re-inserting.
    Populates stats dict with ingestion metrics if provided.
    Returns total inserted chunk count.
    """
    target_pdf = pdf_path or DEFAULT_SOURCE_URI
    if not os.path.exists(target_pdf):
        # Fallback check relative to repository root
        target_pdf = os.path.join(os.getcwd(), DEFAULT_SOURCE_URI)

    logger.info(f"Extracting pages 1-157 from PDF: {target_pdf}")
    pages_text = extract_pages(target_pdf, start_page=1, end_page=157)

    logger.info(f"Parsing chapters and sections across {len(pages_text)} pages...")
    chunk_dicts = parse_chapters_and_sections(
        pages_text, source_uri=DEFAULT_SOURCE_URI, stats=stats
    )
    logger.info(f"Generated {len(chunk_dicts)} statute chunks.")

    # Idempotency: Delete existing chunks for this source_uri first
    logger.info(
        f"Deleting existing statute chunks for source_uri: {DEFAULT_SOURCE_URI}..."
    )
    await session.execute(
        delete(StatuteChunk).where(StatuteChunk.source_uri == DEFAULT_SOURCE_URI)
    )
    await session.commit()

    # Bulk insert StatuteChunk objects
    logger.info(
        f"Bulk inserting {len(chunk_dicts)} StatuteChunk records into PostgreSQL..."
    )
    statute_objects = [
        StatuteChunk(
            act=c["act"],
            act_short=c["act_short"],
            chapter=c["chapter"],
            chapter_title=c["chapter_title"],
            section_number=c["section_number"],
            section_title=c["section_title"],
            subsection=c["subsection"],
            clause=c["clause"],
            text=c["text"],
            has_illustration=c["has_illustration"],
            has_proviso=c["has_proviso"],
            has_exception=c["has_exception"],
            needs_review=c.get("needs_review", False),
            page_start=c["page_start"],
            page_end=c["page_end"],
            chunk_id=c["chunk_id"],
            source_uri=c["source_uri"],
            references_json=c["references_json"],
            embedding=None,  # Embedding vector populated in later step
        )
        for c in chunk_dicts
    ]

    session.add_all(statute_objects)
    await session.commit()
    logger.info(
        f"Successfully loaded {len(statute_objects)} statute chunks to database."
    )

    return len(statute_objects)
