"""
Standalone CLI ingestion script for narrative BNSS text (pages 1-157).
Supports structure-aware chunking and dense vector embedding population.

Usage:
    python scripts/ingest_bns.py                    # Chunking and relational ingestion only
    python scripts/ingest_bns.py --with-embeddings  # Full pipeline including BGE embeddings
"""

import sys
import os
import argparse
import asyncio
from sqlalchemy import select, func

# Ensure standard output doesn't crash on windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure backend folder is in PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

from app.core.db import AsyncSessionLocal, init_db
from app.core.models import StatuteChunk
from app.ingestion.loader import load_statute_chunks_to_db
from app.ingestion.embed_loader import populate_statute_embeddings


async def run_ingestion(with_embeddings: bool = False):
    print("==================================================================")
    print("      NYAYA LEGAL ASSISTANT -- BNSS NARRATIVE INGESTION SCRIPT     ")
    print("==================================================================")

    # 1. Initialize DB and pgvector extension
    print("\n[1/4] Initializing Database & PgVector extension...")
    await init_db()

    # 2. Run Idempotent Ingestion
    print("\n[2/4] Executing Statute Chunk Ingestion (Pages 1-157)...")
    ingestion_stats = {}
    async with AsyncSessionLocal() as session:
        total_loaded = await load_statute_chunks_to_db(session, stats=ingestion_stats)

    # 3. Query Database Statistics & Summarize
    print("\n[3/4] Querying Database Summary Metrics & Chunk Risk Analysis...")
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

        # Needs review count
        result_review = await session.execute(
            select(func.count(StatuteChunk.id)).where(StatuteChunk.needs_review == True)
        )
        needs_review_count = result_review.scalar()

        # Chunk lengths analysis
        all_lengths_stmt = select(StatuteChunk.chunk_id, func.length(StatuteChunk.text)).order_by(func.length(StatuteChunk.text))
        all_lengths = (await session.execute(all_lengths_stmt)).all()

        lengths_only = [l[1] for l in all_lengths]
        max_chunk_len = max(lengths_only) if lengths_only else 0
        p95_idx = int(len(lengths_only) * 0.95) if lengths_only else 0
        p95_chunk_len = lengths_only[p95_idx] if lengths_only else 0

        # Chunks exceeding 2000 characters
        oversized_chunks = [(l[0], l[1]) for l in all_lengths if l[1] > 2000]

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
    print(f" Chunks marked needs_review (pre-embedding):    {needs_review_count}")
    print(f" Total Sections Triggering Clause Fallback:     {fallback_count}")
    print("------------------------------------------------------------------")
    print(f" Chunk Length Statistics (Characters):")
    print(f"   - Max Chunk Length:                          {max_chunk_len} chars")
    print(f"   - p95 Chunk Length:                          {p95_chunk_len} chars")
    print(f"   - Chunks > 2000 chars (Risk Zone):           {len(oversized_chunks)}")
    if oversized_chunks:
        print("   - Oversized Chunk IDs (> 2000 chars):")
        for cid, clen in oversized_chunks:
            print(f"       * {cid} ({clen} chars)")
    print("==================================================================")
    print(f" Fallback Triggering Section Numbers ({fallback_count}):")
    print(f"   {fallback_sections}")
    print("==================================================================")
    print(" Sample Chunks:")
    for s in samples:
        print(f"   - {s.chunk_id} | Ch. {s.chapter} | Sec. {s.section_number}: {s.section_title}")
    print("==================================================================")

    # 4. Dense Vector Embeddings Population (if requested)
    if with_embeddings:
        print("\n[4/4] Populating BAAI/bge-base-en-v1.5 Dense Embeddings...")
        async with AsyncSessionLocal() as session:
            emb_stats = await populate_statute_embeddings(session)

        # Re-check needs_review after token truncation checks
        async with AsyncSessionLocal() as session:
            final_review_res = await session.execute(
                select(func.count(StatuteChunk.id)).where(StatuteChunk.needs_review == True)
            )
            final_needs_review = final_review_res.scalar()

            embedded_res = await session.execute(
                select(func.count(StatuteChunk.id)).where(StatuteChunk.embedding.isnot(None))
            )
            total_embedded_db = embedded_res.scalar()

        print("\n==================================================================")
        print("                      EMBEDDINGS SUMMARY                          ")
        print("==================================================================")
        print(f" Total Chunks with Embeddings in DB:            {total_embedded_db} / {total_count}")
        print(f" Embedding Wall-Clock Time:                     {emb_stats['wall_clock_seconds']} seconds")
        print(f" Throughput:                                    {emb_stats['throughput_chunks_per_sec']} chunks/sec")
        print(f" Truncation Warnings (> 512 tokens):            {emb_stats['truncation_warnings']}")
        if emb_stats['truncated_chunk_ids']:
            print(f" Truncated Chunk IDs (needs_review=True):")
            for t_cid in emb_stats['truncated_chunk_ids']:
                print(f"   - {t_cid}")
        print(f" Total Chunks with needs_review = True:         {final_needs_review}")
        print("==================================================================\n")
    else:
        print("\n[*] Embeddings skipped. To compute and populate vector embeddings, re-run with:")
        print("    python scripts/ingest_bns.py --with-embeddings\n")


def main():
    parser = argparse.ArgumentParser(description="Ingest BNSS statute text and populate embeddings.")
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Generate and populate BAAI/bge-base-en-v1.5 dense embeddings for all statute chunks."
    )
    args = parser.parse_args()
    asyncio.run(run_ingestion(with_embeddings=args.with_embeddings))


if __name__ == "__main__":
    main()
