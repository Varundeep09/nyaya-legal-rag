"""
Database loader for First Schedule OffenceClassification records.
Idempotent delete-and-insert pipeline following the loader.py pattern.
"""

from typing import Tuple

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.models import OffenceClassification
from app.ingestion.bns_chunker import extract_pages
from app.ingestion.schedule_parser import (
    DEFAULT_PDF_PATH,
    DEFAULT_SOURCE_URI,
    SCHEDULE_END_PAGE,
    SCHEDULE_START_PAGE,
    parse_first_schedule,
)


async def load_offence_classification_to_db(
    session: AsyncSession,
    source_uri: str = DEFAULT_SOURCE_URI,
    pdf_path: str = DEFAULT_PDF_PATH,
) -> Tuple[int, int]:
    """
    Extracts, parses, and persists all First Schedule rows into PostgreSQL.
    Idempotent: deletes existing rows for the given source_uri first.

    Returns:
        Tuple of (total_inserted_count, needs_review_count)
    """
    logger.info(
        "Extracting First Schedule pages %d-%d from %s...",
        SCHEDULE_START_PAGE,
        SCHEDULE_END_PAGE,
        pdf_path,
    )
    pages_data = extract_pages(
        pdf_path, start_page=SCHEDULE_START_PAGE, end_page=SCHEDULE_END_PAGE
    )

    logger.info("Parsing First Schedule rows from %d pages...", len(pages_data))
    records = parse_first_schedule(pages_data, source_uri=source_uri)

    if not records:
        logger.warning("No First Schedule records parsed.")
        return 0, 0

    # Idempotent delete of existing rows for this source_uri
    logger.info(
        "Deleting existing offence_classification rows for source_uri: %s", source_uri
    )
    await session.execute(
        delete(OffenceClassification).where(
            OffenceClassification.source_uri == source_uri
        )
    )

    # Bulk insert parsed records
    logger.info(
        "Bulk inserting %d OffenceClassification records into PostgreSQL...",
        len(records),
    )
    db_objects = [
        OffenceClassification(
            bns_section=r["bns_section"],
            offence_description=r["offence_description"],
            punishment=r["punishment"],
            cognizable=r["cognizable"],
            bailable=r["bailable"],
            triable_court=r["triable_court"],
            needs_review=r["needs_review"],
            page_number=r["page_number"],
            source_uri=r["source_uri"],
            embedding=None,
        )
        for r in records
    ]

    session.add_all(db_objects)
    await session.commit()

    needs_review_count = sum(1 for r in records if r["needs_review"])
    logger.info(
        "Successfully committed %d offence_classification rows (%d needs_review=True).",
        len(records),
        needs_review_count,
    )

    return len(records), needs_review_count
