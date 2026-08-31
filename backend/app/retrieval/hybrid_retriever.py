"""
Hybrid retrieval engine combining pgvector dense cosine search, in-process BM25 sparse search,
and Reciprocal Rank Fusion (RRF), with deterministic direct section lookup bypass.
"""

from typing import List, Dict, Any, Optional, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.core.models import StatuteChunk
from app.core.logging import logger
from app.retrieval.embeddings import embed_query
from app.retrieval.bm25_index import get_or_build_bm25_index, search_bm25
from app.retrieval.direct_lookup import detect_section_intent, fetch_section_directly


async def dense_search(
    session: AsyncSession,
    query_text: str,
    top_k: int = 10,
    chapter_filter: Optional[str] = None,
    act_filter: Optional[str] = None,
    section_filter: Optional[str] = None
) -> List[Tuple[str, float]]:
    """
    Performs dense semantic retrieval using BAAI/bge-base-en-v1.5 embeddings
    and pgvector cosine distance directly in PostgreSQL.
    
    Applies metadata filters (chapter, act, section) as native SQL WHERE clauses.
    
    Returns:
        List of (chunk_id, cosine_similarity) sorted descending by similarity.
    """
    if not query_text:
        return []

    # Generate query embedding (includes 'query: ' asymmetric prefix and L2 normalization)
    query_emb = embed_query(query_text)

    # Cosine distance operator (<=>): distance = 1 - cosine_similarity
    cosine_dist = StatuteChunk.embedding.cosine_distance(query_emb)
    similarity = (1.0 - cosine_dist).label("similarity")

    stmt = (
        select(StatuteChunk.chunk_id, similarity)
        .where(StatuteChunk.embedding.isnot(None))
    )

    # Apply native DB-level metadata filters
    if chapter_filter:
        stmt = stmt.where(StatuteChunk.chapter == chapter_filter)
    if act_filter:
        stmt = stmt.where(
            or_(
                StatuteChunk.act == act_filter,
                StatuteChunk.act_short == act_filter
            )
        )
    if section_filter:
        stmt = stmt.where(StatuteChunk.section_number == str(section_filter))

    stmt = stmt.order_by(cosine_dist.asc()).limit(top_k)

    result = await session.execute(stmt)
    rows = result.all()
    return [(r[0], float(r[1])) for r in rows]


def reciprocal_rank_fusion(
    dense_results: List[Tuple[str, float]],
    bm25_results: List[Tuple[str, float]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    Fuses ranked dense and sparse results using Reciprocal Rank Fusion (RRF).
    
    RRF Score formula:
        RRF_score(d) = sum_{m in models} (1.0 / (k + rank_m(d)))
    
    NOTE ON PARAMETER k=60:
    The constant k=60 is the empirical standard established by Cormack, Clarke,
    and Buettcher (SIGIR 2009). It prevents top-ranked outliers in either list
    from dominating the fused score while maintaining high recall.
    
    Args:
        dense_results: List of (chunk_id, dense_score) from vector search.
        bm25_results: List of (chunk_id, bm25_score) from BM25 sparse search.
        k: Smoothing constant (default 60).
        
    Returns:
        List of dicts with fused score and per-model rank/score for debuggability,
        sorted descending by rrf_score.
    """
    fused_map: Dict[str, Dict[str, Any]] = {}

    # Accumulate dense ranks
    for rank, (chunk_id, score) in enumerate(dense_results, start=1):
        if chunk_id not in fused_map:
            fused_map[chunk_id] = {
                "chunk_id": chunk_id,
                "rrf_score": 0.0,
                "dense_rank": rank,
                "dense_score": score,
                "bm25_rank": None,
                "bm25_score": None
            }
        else:
            fused_map[chunk_id]["dense_rank"] = rank
            fused_map[chunk_id]["dense_score"] = score
        fused_map[chunk_id]["rrf_score"] += 1.0 / (k + rank)

    # Accumulate BM25 ranks
    for rank, (chunk_id, score) in enumerate(bm25_results, start=1):
        if chunk_id not in fused_map:
            fused_map[chunk_id] = {
                "chunk_id": chunk_id,
                "rrf_score": 0.0,
                "dense_rank": None,
                "dense_score": None,
                "bm25_rank": rank,
                "bm25_score": score
            }
        else:
            fused_map[chunk_id]["bm25_rank"] = rank
            fused_map[chunk_id]["bm25_score"] = score
        fused_map[chunk_id]["rrf_score"] += 1.0 / (k + rank)

    # Sort descending by fused RRF score
    sorted_fused = sorted(fused_map.values(), key=lambda x: x["rrf_score"], reverse=True)
    return sorted_fused


async def hybrid_search(
    session: AsyncSession,
    query_text: str,
    top_k: int = 10,
    chapter_filter: Optional[str] = None,
    act_filter: Optional[str] = None,
    section_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Main retrieval entrypoint for Nyaya:
    1. Direct Section Lookup Check:
       If query explicitly asks for a section (e.g. 'what is section 103 bnss'),
       bypasses similarity search and returns all chunks for that section deterministically.
    2. Hybrid Search Path:
       - Runs dense cosine search against pgvector with SQL filters.
       - Runs sparse BM25 search over corpus text.
       - Applies metadata filtering to sparse candidates.
       - Fuses results via Reciprocal Rank Fusion (k=60).
       - Hydrates top_k chunk records from PostgreSQL.
       
    Returns:
        List of complete chunk dictionaries with metadata and score fields.
    """
    logger.info("Executing hybrid_search for query: '%s' (top_k=%d)", query_text, top_k)

    # 1. Check for Direct Section Lookup intent
    detected_section = detect_section_intent(query_text)
    if (
        detected_section is not None
        and not chapter_filter
        and not act_filter
        and (not section_filter or section_filter == detected_section)
    ):
        direct_results = await fetch_section_directly(session, detected_section)
        if direct_results:
            logger.info("Direct section lookup resolved %d chunks for Section %s.", len(direct_results), detected_section)
            return direct_results[:top_k]

    # 2. Run Dense & Sparse Search
    candidate_depth = max(top_k * 3, 30)

    # Dense Search
    dense_results = await dense_search(
        session=session,
        query_text=query_text,
        top_k=candidate_depth,
        chapter_filter=chapter_filter,
        act_filter=act_filter,
        section_filter=section_filter
    )

    # Sparse BM25 Search
    bm25_index, chunk_id_list = await get_or_build_bm25_index(session)
    bm25_all = search_bm25(bm25_index, chunk_id_list, query_text, top_k=len(chunk_id_list))

    # If filters are provided, filter BM25 candidates to matching chunk_ids
    if chapter_filter or act_filter or section_filter:
        filter_stmt = select(StatuteChunk.chunk_id)
        if chapter_filter:
            filter_stmt = filter_stmt.where(StatuteChunk.chapter == chapter_filter)
        if act_filter:
            filter_stmt = filter_stmt.where(
                or_(
                    StatuteChunk.act == act_filter,
                    StatuteChunk.act_short == act_filter
                )
            )
        if section_filter:
            filter_stmt = filter_stmt.where(StatuteChunk.section_number == str(section_filter))

        valid_ids_res = await session.execute(filter_stmt)
        valid_chunk_ids: Set[str] = set(valid_ids_res.scalars().all())
        bm25_results = [(cid, sc) for cid, sc in bm25_all if cid in valid_chunk_ids][:candidate_depth]
    else:
        bm25_results = bm25_all[:candidate_depth]

    # 3. Fuse via Reciprocal Rank Fusion
    fused_ranks = reciprocal_rank_fusion(dense_results, bm25_results, k=60)
    top_fused = fused_ranks[:top_k]

    if not top_fused:
        logger.info("Hybrid search returned 0 matching results.")
        return []

    top_chunk_ids = [item["chunk_id"] for item in top_fused]
    fused_meta_map = {item["chunk_id"]: item for item in top_fused}

    # 4. Hydrate full records from DB
    stmt = select(StatuteChunk).where(StatuteChunk.chunk_id.in_(top_chunk_ids))
    result = await session.execute(stmt)
    chunks = result.scalars().all()
    chunk_by_id = {c.chunk_id: c for c in chunks}

    # 5. Assemble final ordered result list
    final_results = []
    for cid in top_chunk_ids:
        chunk = chunk_by_id.get(cid)
        if not chunk:
            continue
        meta = fused_meta_map[cid]
        final_results.append({
            "chunk_id": chunk.chunk_id,
            "act": chunk.act,
            "act_short": chunk.act_short,
            "chapter": chunk.chapter,
            "chapter_title": chunk.chapter_title,
            "section_number": chunk.section_number,
            "section_title": chunk.section_title,
            "subsection": chunk.subsection,
            "clause": chunk.clause,
            "text": chunk.text,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "has_proviso": chunk.has_proviso,
            "has_illustration": chunk.has_illustration,
            "has_exception": chunk.has_exception,
            "references_json": chunk.references_json,
            "retrieval_method": "hybrid_rrf",
            "score": round(meta["rrf_score"], 6),
            "dense_score": round(meta["dense_score"], 4) if meta["dense_score"] is not None else None,
            "dense_rank": meta["dense_rank"],
            "bm25_score": round(meta["bm25_score"], 4) if meta["bm25_score"] is not None else None,
            "bm25_rank": meta["bm25_rank"]
        })

    logger.info("Hybrid search retrieved %d ranked chunks.", len(final_results))
    return final_results
