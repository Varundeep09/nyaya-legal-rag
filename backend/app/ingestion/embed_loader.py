"""
Async module to populate dense vector embeddings for statute chunks in PostgreSQL.
"""

import time
from typing import Dict, Any, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import StatuteChunk
from app.core.logging import logger
from app.retrieval.embeddings import (
    embed_passages,
    check_token_length,
    get_embedding_model,
)


async def populate_statute_embeddings(
    session: AsyncSession, batch_size: int = 32
) -> Dict[str, Any]:
    """
    Populates vector embeddings for all statute chunks where embedding IS NULL.
    Checks real token length per chunk and marks needs_review=True if truncated.
    Returns summary statistics including wall-clock time and throughput.
    """
    # Ensure embedding model is loaded & validated
    model = get_embedding_model()
    max_seq_len = model.max_seq_length

    # 1. Fetch chunks where embedding IS NULL
    stmt = (
        select(
            StatuteChunk.id,
            StatuteChunk.chunk_id,
            StatuteChunk.text,
            StatuteChunk.needs_review,
        )
        .where(StatuteChunk.embedding.is_(None))
        .order_by(StatuteChunk.chunk_id)
    )
    result = await session.execute(stmt)
    unembedded_rows = result.all()

    total_chunks = len(unembedded_rows)
    if total_chunks == 0:
        logger.info("All statute chunks already have embeddings. Nothing to populate.")
        return {
            "total_embedded": 0,
            "wall_clock_seconds": 0.0,
            "throughput_chunks_per_sec": 0.0,
            "truncation_warnings": 0,
            "truncated_chunk_ids": [],
        }

    logger.info(
        f"Populating embeddings for {total_chunks} statute chunks in batches of {batch_size}..."
    )
    print(f"\n[Embedding Pipeline] Starting embedding for {total_chunks} chunks...")

    start_time = time.perf_counter()
    truncated_chunks: List[str] = []

    # 2. Check token length & pre-process truncation warnings
    chunk_updates = []
    for row in unembedded_rows:
        row_id, chunk_id, text, current_needs_review = row
        is_exceeded, token_count = check_token_length(text)
        needs_review = current_needs_review or is_exceeded

        if is_exceeded:
            truncated_chunks.append(chunk_id)
            print(
                f"  [TRUNCATION WARNING] {chunk_id}: {token_count} tokens exceeds max_seq_length ({max_seq_len}) -> marked needs_review=True"
            )

        chunk_updates.append(
            {
                "id": row_id,
                "chunk_id": chunk_id,
                "text": text,
                "needs_review": needs_review,
            }
        )

    # 3. Process in batches: embed and update DB
    for i in range(0, total_chunks, batch_size):
        batch = chunk_updates[i : i + batch_size]
        batch_texts = [b["text"] for b in batch]

        # Compute dense embeddings
        batch_vectors = embed_passages(batch_texts, batch_size=batch_size)

        # Update each row in session
        for item, vector in zip(batch, batch_vectors):
            await session.execute(
                update(StatuteChunk)
                .where(StatuteChunk.id == item["id"])
                .values(embedding=vector, needs_review=item["needs_review"])
            )

        await session.commit()
        processed_so_far = min(i + batch_size, total_chunks)
        elapsed = time.perf_counter() - start_time
        rate = processed_so_far / elapsed if elapsed > 0 else 0
        print(
            f"  [Embedding Progress] {processed_so_far}/{total_chunks} chunks embedded ({rate:.1f} chunks/sec)..."
        )

    total_time = time.perf_counter() - start_time
    overall_throughput = total_chunks / total_time if total_time > 0 else 0.0

    print(
        f"\n[Embedding Pipeline] Successfully embedded {total_chunks} chunks in {total_time:.2f}s ({overall_throughput:.1f} chunks/sec)."
    )

    return {
        "total_embedded": total_chunks,
        "wall_clock_seconds": round(total_time, 2),
        "throughput_chunks_per_sec": round(overall_throughput, 1),
        "truncation_warnings": len(truncated_chunks),
        "truncated_chunk_ids": truncated_chunks,
    }
