"""
Standalone CLI ingestion script for narrative BNSS text (pages 1-157).
Run via: python scripts/ingest_bns.py
"""

import sys
import os
import asyncio
from sqlalchemy import select, func

# Ensure backend folder is in PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

from app.core.db import AsyncSessionLocal, init_db
from app.core.models import StatuteChunk
from app.ingestion.loader import load_statute_chunks_to_db


async def main():
    print("==================================================================")
    print("      NYAYA LEGAL ASSISTANT — BNSS NARRATIVE INGESTION SCRIPT     ")
    print("==================================================================")

    # 1. Initialize DB and pgvector extension
    print("\n[1/3] Initializing Database & PgVector extension...")
    await init_db()

    # 2. Run Idempotent Ingestion
    print("\n[2/3] Executing Statute Chunk Ingestion (Pages 1-157)...")
    ingestion_stats = {}
    async with AsyncSessionLocal() as session:
        total_loaded = await load_statute_chunks_to_db(session, stats=ingestion_stats)

    # 3. Query Database Statistics & Summarize
    print("\n[3/3] Querying Database Summary Metrics...")
    async with AsyncSessionLocal() as session:
        # Total chunks count
        result_total = await session.execute(select(func.count(StatuteChunk.id)))
        total_count = result_total.scalar()

        # Provisos count
        result_proviso = await session.execute(
            select(func.count(StatuteChunk.id)).where(StatuteChunk.has_proviso == True)
        )
        proviso_count = result_proviso.scalar()

        # Illustrations count
        result_illus = await session.execute(
            select(func.count(StatuteChunk.id)).where(StatuteChunk.has_illustration == True)
        )
        illus_count = result_illus.scalar()

        # Non-empty references count
        result_refs = await session.execute(
            select(func.count(StatuteChunk.id)).where(func.jsonb_array_length(StatuteChunk.references_json) > 0)
        )
        refs_count = result_refs.scalar()

        # Fetch sample chunks for display
        sample_stmt = select(StatuteChunk.chunk_id, StatuteChunk.chapter, StatuteChunk.section_number, StatuteChunk.section_title).limit(5)
        samples = (await session.execute(sample_stmt)).all()

    fallback_count = ingestion_stats.get("fallback_count", 0)
    fallback_sections = ingestion_stats.get("fallback_sections", [])

    print("\n==================================================================")
    print("                        INGESTION SUMMARY                         ")
    print("==================================================================")
    print(f" Total Statute Chunks Inserted:                 {total_count}")
    print(f" Chunks with Provisos (has_proviso):             {proviso_count}")
    print(f" Chunks with Illustrations:                     {illus_count}")
    print(f" Chunks with Cross-References:                  {refs_count}")
    print(f" Total Sections Triggering Clause Fallback:     {fallback_count}")
    print("==================================================================")
    print(f" Fallback Triggering Section Numbers ({fallback_count}):")
    print(f"   {fallback_sections}")
    print("==================================================================")
    print(" Sample Chunks:")
    for s in samples:
        print(f"   - {s.chunk_id} | Ch. {s.chapter} | Sec. {s.section_number}: {s.section_title}")
    print("==================================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
