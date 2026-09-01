"""
Standalone CLI ingestion script for First Schedule (Classification of Offences, pages 158-189).
Supports relational ingestion and dense vector embedding population for BNS offences.

Usage:
    python scripts/ingest_schedule.py                    # Parsing and relational ingestion only
    python scripts/ingest_schedule.py --with-embeddings  # Full pipeline including BGE embeddings
"""

import sys
import os
import time
import argparse
import asyncio
from sqlalchemy import select, func, update

# Ensure standard output doesn't crash on windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure backend folder is in PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

from app.core.db import AsyncSessionLocal, init_db
from app.core.models import OffenceClassification
from app.core.logging import logger
from app.ingestion.schedule_loader import load_offence_classification_to_db
from app.retrieval.embeddings import (
    embed_passages,
    check_token_length,
)


async def populate_schedule_embeddings(batch_size: int = 32):
    """
    Computes BGE embeddings for all OffenceClassification rows with NULL embeddings.
    """
    logger.info("Populating embeddings for OffenceClassification records...")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                OffenceClassification.id,
                OffenceClassification.bns_section,
                OffenceClassification.offence_description,
            ).order_by(OffenceClassification.page_number, OffenceClassification.id)
        )
        records = result.all()

        total = len(records)
        logger.info(
            "Populating embeddings for %d First Schedule records in batches of %d...",
            total,
            batch_size,
        )
        print(
            f"\n[Embedding Pipeline] Starting embedding for {total} offence classification records..."
        )

        start_time = time.perf_counter()
        truncated_count = 0

        for i in range(0, total, batch_size):
            batch = records[i : i + batch_size]
            batch_ids = [r[0] for r in batch]
            batch_texts = [r[2] for r in batch]

            # Check token lengths
            for r in batch:
                is_exceeded, token_cnt = check_token_length(r[2])
                if is_exceeded:
                    truncated_count += 1
                    logger.warning(
                        "Truncation warning for BNS %s: %d tokens exceeds 512 max length.",
                        r[1],
                        token_cnt,
                    )

            # Generate embeddings
            vectors = embed_passages(batch_texts, batch_size=len(batch_texts))

            # Update database
            for row_id, vec in zip(batch_ids, vectors):
                await session.execute(
                    update(OffenceClassification)
                    .where(OffenceClassification.id == row_id)
                    .values(embedding=vec)
                )

            await session.commit()
            elapsed = time.perf_counter() - start_time
            rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
            print(
                f"  [Embedding Progress] {min(i + batch_size, total)}/{total} records embedded ({rate:.1f} rows/sec)..."
            )

        total_time = time.perf_counter() - start_time
        avg_rate = total / total_time if total_time > 0 else 0
        print(
            f"\n[Embedding Pipeline] Successfully embedded {total} records in {total_time:.2f}s ({avg_rate:.1f} rows/sec)."
        )

        return {
            "total_embedded": total,
            "wall_clock_time": total_time,
            "throughput": avg_rate,
            "truncated_count": truncated_count,
        }


async def run_schedule_ingestion(with_embeddings: bool = False):
    print("==================================================================")
    print("   NYAYA LEGAL ASSISTANT -- FIRST SCHEDULE INGESTION SCRIPT      ")
    print("==================================================================")

    # 1. Initialize DB and pgvector extension
    print("\n[1/4] Initializing Database & PgVector extension...")
    await init_db()

    # 2. Run Idempotent Ingestion
    print("\n[2/4] Executing First Schedule Ingestion (Pages 158-189)...")
    async with AsyncSessionLocal() as session:
        total_loaded, needs_review_count = await load_offence_classification_to_db(
            session
        )

    # 3. Query Database Statistics & Summarize
    print("\n[3/4] Querying Database Summary Metrics & Classification Statistics...")
    async with AsyncSessionLocal() as session:
        result_total = await session.execute(
            select(func.count(OffenceClassification.id))
        )
        total_count = result_total.scalar()

        result_review = await session.execute(
            select(func.count(OffenceClassification.id)).where(
                OffenceClassification.needs_review.is_(True)
            )
        )
        review_count = result_review.scalar()

        result_cog = await session.execute(
            select(func.count(OffenceClassification.id)).where(
                OffenceClassification.cognizable.ilike("%Cognizable%")
            )
        )
        cognizable_count = result_cog.scalar()

        result_non_cog = await session.execute(
            select(func.count(OffenceClassification.id)).where(
                OffenceClassification.cognizable.ilike("%Non-cognizable%")
            )
        )
        non_cognizable_count = result_non_cog.scalar()

        result_bail = await session.execute(
            select(func.count(OffenceClassification.id)).where(
                OffenceClassification.bailable.ilike("%Bailable%")
            )
        )
        bailable_count = result_bail.scalar()

        sample_stmt = select(
            OffenceClassification.bns_section,
            OffenceClassification.cognizable,
            OffenceClassification.bailable,
            OffenceClassification.triable_court,
        ).limit(5)
        samples = (await session.execute(sample_stmt)).all()

    print("\n==================================================================")
    print("                    FIRST SCHEDULE SUMMARY                        ")
    print("==================================================================")
    print(f" Total Schedule Rows Inserted:                 {total_count}")
    print(
        f" Clean Tail Extractions (needs_review=False):   {total_count - review_count}"
    )
    print(f" Tail Extraction Failures (needs_review=True):  {review_count}")
    print(f" Rows with Cognizable Classification:          {cognizable_count}")
    print(f" Rows with Non-Cognizable Classification:      {non_cognizable_count}")
    print(f" Rows with Bailable Classification:            {bailable_count}")
    print("==================================================================")
    print(" Sample Classifications:")
    for s in samples:
        print(
            f"   - BNS Sec {s[0]:8s} | Cog: {s[1] or 'N/A':15s} | Bail: {s[2] or 'N/A':15s} | Court: {s[3] or 'N/A'}"
        )
    print("==================================================================")

    # 4. Dense Vector Embeddings
    if with_embeddings:
        print("\n[4/4] Populating BAAI/bge-base-en-v1.5 Dense Embeddings...")
        embed_stats = await populate_schedule_embeddings(batch_size=32)

        print("\n==================================================================")
        print("                      EMBEDDINGS SUMMARY                          ")
        print("==================================================================")
        print(
            f" Total Rows with Embeddings in DB:             {embed_stats['total_embedded']} / {total_count}"
        )
        print(
            f" Embedding Wall-Clock Time:                     {embed_stats['wall_clock_time']:.2f} seconds"
        )
        print(
            f" Throughput:                                    {embed_stats['throughput']:.1f} rows/sec"
        )
        print(
            f" Truncation Warnings (> 512 tokens):            {embed_stats['truncated_count']}"
        )
        print("==================================================================\n")
    else:
        print(
            "\n[4/4] Skipping embeddings population (pass --with-embeddings to compute)."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Ingest First Schedule BNS offence classifications into Nyaya."
    )
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Generate and populate BAAI/bge-base-en-v1.5 dense embeddings for offence descriptions.",
    )
    args = parser.parse_args()
    asyncio.run(run_schedule_ingestion(with_embeddings=args.with_embeddings))


if __name__ == "__main__":
    main()
