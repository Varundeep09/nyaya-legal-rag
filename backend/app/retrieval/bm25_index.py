"""
In-process BM25Okapi sparse retrieval index over statute chunks.
Maintains an in-memory index built from PostgreSQL statute_chunk text.
Preserves numbers and alphanumeric tokens intact for precise legal cross-referencing.
"""

import re
from typing import List, Tuple, Optional
from rank_bm25 import BM25Okapi
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.models import StatuteChunk
from app.core.logging import logger

# Module-level cache for the BM25 index and chunk ID list
_CACHED_BM25_INDEX: Optional[BM25Okapi] = None
_CACHED_CHUNK_IDS: Optional[List[str]] = None


def tokenize(text: str) -> List[str]:
    """
    Tokenizes text by converting to lowercase and splitting on non-alphanumeric boundaries.
    Crucially preserves bare numbers (e.g. section numbers '103', '35') as their own tokens,
    without stripping digits as stopwords.
    """
    if not text:
        return []
    return re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())


async def build_bm25_index(session: AsyncSession) -> Tuple[BM25Okapi, List[str]]:
    """
    Fetches all statute_chunk rows from PostgreSQL, tokenizes their text fields,
    and builds an in-memory BM25Okapi index.
    
    Returns:
        Tuple of (bm25_index, chunk_id_list) where chunk_id_list[i] maps back
        to the statute_chunk.chunk_id for BM25 document i.
    """
    logger.info("Building in-memory BM25 index from statute_chunk records...")
    stmt = select(StatuteChunk.chunk_id, StatuteChunk.text).order_by(StatuteChunk.id)
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        logger.warning("No statute_chunk records found when building BM25 index.")
        return BM25Okapi([[]]), []

    chunk_ids = [r[0] for r in rows]
    tokenized_corpus = [tokenize(r[1]) for r in rows]

    bm25 = BM25Okapi(tokenized_corpus)
    logger.info("Successfully built BM25 index for %d chunks.", len(chunk_ids))
    return bm25, chunk_ids


def search_bm25(
    bm25_index: BM25Okapi,
    chunk_id_list: List[str],
    query: str,
    top_k: int = 10
) -> List[Tuple[str, float]]:
    """
    Searches the BM25 index for a given query and returns top_k results.
    
    Args:
        bm25_index: The initialized BM25Okapi index.
        chunk_id_list: List of chunk_ids corresponding 1-to-1 with documents in index.
        query: Search query text.
        top_k: Maximum number of ranked results to return.
        
    Returns:
        List of (chunk_id, bm25_score) sorted descending by score.
    """
    if not chunk_id_list or not query:
        return []

    tokenized_query = tokenize(query)
    if not tokenized_query:
        return []

    scores = bm25_index.get_scores(tokenized_query)
    ranked = sorted(zip(chunk_id_list, scores), key=lambda x: x[1], reverse=True)
    return [(cid, float(sc)) for cid, sc in ranked[:top_k]]


async def get_or_build_bm25_index(session: AsyncSession) -> Tuple[BM25Okapi, List[str]]:
    """
    Returns the cached in-process BM25Okapi index and chunk_id mapping,
    or lazily builds it once from PostgreSQL on first access.
    
    NOTE ON CORPUS MUTATION:
    Since the statutory legal corpus (BNSS bare act) is static after ingestion,
    this in-memory cache remains valid for the full lifetime of the application process.
    If the corpus is ever re-ingested or mutated post-startup, this cache must be
    invalidated via `invalidate_bm25_cache()`.
    """
    global _CACHED_BM25_INDEX, _CACHED_CHUNK_IDS
    if _CACHED_BM25_INDEX is None or _CACHED_CHUNK_IDS is None:
        _CACHED_BM25_INDEX, _CACHED_CHUNK_IDS = await build_bm25_index(session)
    return _CACHED_BM25_INDEX, _CACHED_CHUNK_IDS


def invalidate_bm25_cache() -> None:
    """Invalidates the module-level BM25 cache."""
    global _CACHED_BM25_INDEX, _CACHED_CHUNK_IDS
    _CACHED_BM25_INDEX = None
    _CACHED_CHUNK_IDS = None
    logger.info("BM25 cache invalidated.")
