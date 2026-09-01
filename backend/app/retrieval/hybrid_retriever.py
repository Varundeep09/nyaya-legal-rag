"""
Hybrid retrieval engine combining pgvector dense cosine search, in-process BM25 sparse search,
and Reciprocal Rank Fusion (RRF), with deterministic direct section lookup bypass.
Supports both statutory procedure chunks (BNSS) and offence classifications (BNS First Schedule).
"""

import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.models import (
    OffenceClassification,
    StatuteChunk,
    UserDocument,
    UserDocumentChunk,
)
from app.retrieval.bm25_index import get_or_build_bm25_index, search_bm25
from app.retrieval.direct_lookup import (
    detect_act_and_section_intent,
    fetch_bns_offence_directly,
    fetch_section_directly,
)
from app.retrieval.embeddings import embed_query


async def dense_search(
    session: AsyncSession,
    query_text: str,
    top_k: int = 10,
    chapter_filter: Optional[str] = None,
    act_filter: Optional[str] = None,
    section_filter: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """
    Performs dense semantic retrieval using BAAI/bge-base-en-v1.5 embeddings
    and pgvector cosine distance across both StatuteChunk and OffenceClassification tables.

    Applies metadata filters (chapter, act, section) as native SQL WHERE clauses.

    Returns:
        List of (chunk_id, cosine_similarity) sorted descending by similarity.
    """
    if not query_text:
        return []

    # Generate query embedding (includes 'query: ' asymmetric prefix and L2 normalization)
    query_emb = embed_query(query_text)

    # 1. Search StatuteChunk (BNSS procedure chunks)
    cosine_dist = StatuteChunk.embedding.cosine_distance(query_emb)
    similarity = (1.0 - cosine_dist).label("similarity")

    stmt = select(StatuteChunk.chunk_id, similarity).where(
        StatuteChunk.embedding.isnot(None)
    )

    # Apply native DB-level metadata filters for StatuteChunk
    if chapter_filter:
        stmt = stmt.where(StatuteChunk.chapter == chapter_filter)
    if act_filter:
        stmt = stmt.where(
            or_(StatuteChunk.act == act_filter, StatuteChunk.act_short == act_filter)
        )
    if section_filter:
        stmt = stmt.where(StatuteChunk.section_number == str(section_filter))

    stmt = stmt.order_by(cosine_dist.asc()).limit(top_k)
    result = await session.execute(stmt)
    rows_statute = result.all()
    candidates: List[Tuple[str, float]] = [(r[0], float(r[1])) for r in rows_statute]

    # 2. Search OffenceClassification (BNS First Schedule offences)
    allow_offence = True
    if chapter_filter and chapter_filter not in (
        "FIRST SCHEDULE",
        "THE FIRST SCHEDULE",
        "CLASSIFICATION OF OFFENCES",
        "1",
        "I",
    ):
        allow_offence = False
    if act_filter and act_filter not in (
        "BNS",
        "Bharatiya Nyaya Sanhita, 2023",
        "Bharatiya Nyaya Sanhita",
    ):
        allow_offence = False

    if allow_offence:
        offence_cosine_dist = OffenceClassification.embedding.cosine_distance(query_emb)
        offence_sim = (1.0 - offence_cosine_dist).label("similarity")

        offence_stmt = select(OffenceClassification.id, offence_sim).where(
            OffenceClassification.embedding.isnot(None)
        )
        if section_filter:
            offence_stmt = offence_stmt.where(
                or_(
                    OffenceClassification.bns_section == str(section_filter),
                    OffenceClassification.bns_section.ilike(f"{section_filter}(%)"),
                )
            )
        offence_stmt = offence_stmt.order_by(offence_cosine_dist.asc()).limit(top_k)
        res_offence = await session.execute(offence_stmt)
        for r in res_offence.all():
            candidates.append((f"bns-sched1-{r[0]}", float(r[1])))

    # Sort all dense candidates descending by cosine similarity
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_k]


def reciprocal_rank_fusion(
    dense_results: List[Tuple[str, float]],
    bm25_results: List[Tuple[str, float]],
    k: int = 60,
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
                "bm25_score": None,
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
                "bm25_score": score,
            }
        else:
            fused_map[chunk_id]["bm25_rank"] = rank
            fused_map[chunk_id]["bm25_score"] = score
        fused_map[chunk_id]["rrf_score"] += 1.0 / (k + rank)

    # Sort descending by fused RRF score
    sorted_fused = sorted(
        fused_map.values(), key=lambda x: x["rrf_score"], reverse=True
    )
    return sorted_fused


async def _hydrate_chunks(
    session: AsyncSession,
    top_chunk_ids: List[str],
    meta_map: Dict[str, Dict[str, Any]],
    retrieval_method: str = "hybrid_rrf",
) -> List[Dict[str, Any]]:
    """
    Hydrates full chunk records from both StatuteChunk and OffenceClassification tables
    preserving the exact order of top_chunk_ids.
    """
    statute_ids = [cid for cid in top_chunk_ids if not cid.startswith("bns-sched1-")]
    offence_uuids = []
    for cid in top_chunk_ids:
        if cid.startswith("bns-sched1-"):
            raw_uuid = cid.replace("bns-sched1-", "")
            try:
                offence_uuids.append(uuid.UUID(raw_uuid))
            except ValueError:
                pass

    statute_by_id = {}
    if statute_ids:
        stmt = select(StatuteChunk).where(StatuteChunk.chunk_id.in_(statute_ids))
        res = await session.execute(stmt)
        statute_by_id = {c.chunk_id: c for c in res.scalars().all()}

    offence_by_id = {}
    if offence_uuids:
        stmt = select(OffenceClassification).where(
            OffenceClassification.id.in_(offence_uuids)
        )
        res = await session.execute(stmt)
        offence_by_id = {str(c.id): c for c in res.scalars().all()}

    final_results = []
    for cid in top_chunk_ids:
        meta = meta_map.get(cid, {})
        if cid in statute_by_id:
            chunk = statute_by_id[cid]
            final_results.append(
                {
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
                    "retrieval_method": retrieval_method,
                    "score": round(
                        meta.get("rrf_score", meta.get("dense_score", 1.0)), 6
                    ),
                    "dense_score": (
                        round(meta["dense_score"], 4)
                        if meta.get("dense_score") is not None
                        else None
                    ),
                    "dense_rank": meta.get("dense_rank"),
                    "bm25_score": (
                        round(meta["bm25_score"], 4)
                        if meta.get("bm25_score") is not None
                        else None
                    ),
                    "bm25_rank": meta.get("bm25_rank"),
                }
            )
        elif cid.startswith("bns-sched1-"):
            raw_uuid = cid.replace("bns-sched1-", "")
            if raw_uuid in offence_by_id:
                row = offence_by_id[raw_uuid]
                final_results.append(
                    {
                        "chunk_id": cid,
                        "act": "Bharatiya Nyaya Sanhita, 2023",
                        "act_short": "BNS",
                        "chapter": "FIRST SCHEDULE",
                        "chapter_title": "CLASSIFICATION OF OFFENCES",
                        "section_number": row.bns_section,
                        "section_title": f"BNS Section {row.bns_section}",
                        "subsection": None,
                        "clause": None,
                        "text": (
                            f"BNS Section {row.bns_section}: {row.offence_description}\n"
                            f"Classification: {row.cognizable or 'N/A'}, {row.bailable or 'N/A'}, Triable by: {row.triable_court or 'N/A'}"
                        ),
                        "page_start": row.page_number,
                        "page_end": row.page_number,
                        "has_proviso": False,
                        "has_illustration": False,
                        "has_exception": False,
                        "references_json": [],
                        "retrieval_method": retrieval_method,
                        "score": round(
                            meta.get("rrf_score", meta.get("dense_score", 1.0)), 6
                        ),
                        "cognizable": row.cognizable,
                        "bailable": row.bailable,
                        "triable_court": row.triable_court,
                        "punishment": row.punishment,
                        "dense_score": (
                            round(meta["dense_score"], 4)
                            if meta.get("dense_score") is not None
                            else None
                        ),
                        "dense_rank": meta.get("dense_rank"),
                        "bm25_score": (
                            round(meta["bm25_score"], 4)
                            if meta.get("bm25_score") is not None
                            else None
                        ),
                        "bm25_rank": meta.get("bm25_rank"),
                    }
                )
    return final_results


async def hybrid_search(
    session: AsyncSession,
    query_text: str,
    top_k: int = 10,
    chapter_filter: Optional[str] = None,
    act_filter: Optional[str] = None,
    section_filter: Optional[str] = None,
    retrieval_mode: str = "hybrid",
) -> List[Dict[str, Any]]:
    """
    Main retrieval entrypoint for Nyaya:
    1. Direct Section Lookup Check (if retrieval_mode == 'hybrid'):
       If query explicitly asks for a section (e.g. 'what is section 103 bnss'),
       bypasses similarity search and returns all chunks for that section deterministically.
    2. Hybrid Search Path:
       - Runs dense cosine search against pgvector across statute_chunk & offence_classification.
       - Runs sparse BM25 search over unified corpus text (if retrieval_mode == 'hybrid').
       - Applies metadata filtering to sparse candidates.
       - Fuses results via Reciprocal Rank Fusion (k=60) or dense cosine ranking.
       - Hydrates top_k chunk records from PostgreSQL.

    Returns:
        List of complete chunk dictionaries with metadata and score fields.
    """
    logger.info(
        "Executing %s search for query: '%s' (top_k=%d)",
        retrieval_mode,
        query_text,
        top_k,
    )

    # 1. Check for Direct Section Lookup intent (Hybrid mode only)
    if retrieval_mode == "hybrid":
        intent = detect_act_and_section_intent(query_text)
        if (
            intent is not None
            and not chapter_filter
            and not act_filter
            and (
                not section_filter
                or section_filter in (intent["section"], intent["base_section"])
            )
        ):
            act = intent["act"]
            sec = intent["section"]
            base_sec = intent["base_section"]

            if act == "BNS":
                # Direct BNS offence classification lookup
                bns_results = await fetch_bns_offence_directly(session, sec)
                if not bns_results and sec != base_sec:
                    bns_results = await fetch_bns_offence_directly(session, base_sec)
                if bns_results:
                    logger.info(
                        "Direct BNS offence lookup resolved %d rows for Section %s.",
                        len(bns_results),
                        sec,
                    )
                    return bns_results[:top_k]
            elif act == "BNSS":
                # Direct BNSS statute chunk lookup
                direct_results = await fetch_section_directly(session, base_sec)
                if direct_results:
                    logger.info(
                        "Direct BNSS section lookup resolved %d chunks for Section %s.",
                        len(direct_results),
                        base_sec,
                    )
                    return direct_results[:top_k]
            else:  # AMBIGUOUS
                # Try BNSS statute_chunk first; if no match found, fallback to BNS offence_classification
                direct_results = await fetch_section_directly(session, base_sec)
                if direct_results:
                    logger.info(
                        "Direct section lookup (ambiguous query) resolved %d BNSS chunks for Section %s.",
                        len(direct_results),
                        base_sec,
                    )
                    return direct_results[:top_k]

                bns_results = await fetch_bns_offence_directly(session, sec)
                if bns_results:
                    logger.info(
                        "Direct section lookup fallback resolved %d BNS offence rows for Section %s.",
                        len(bns_results),
                        sec,
                    )
                    return bns_results[:top_k]

    # 2. Run Dense & Sparse Search
    candidate_depth = max(top_k * 3, 30)

    # Dense Search
    dense_results = await dense_search(
        session=session,
        query_text=query_text,
        top_k=candidate_depth if retrieval_mode == "hybrid" else top_k,
        chapter_filter=chapter_filter,
        act_filter=act_filter,
        section_filter=section_filter,
    )

    if retrieval_mode == "dense_only":
        if not dense_results:
            return []
        top_chunk_ids = [cid for cid, _ in dense_results[:top_k]]
        meta_map = {
            cid: {"dense_score": score, "dense_rank": rank}
            for rank, (cid, score) in enumerate(dense_results[:top_k], start=1)
        }
        return await _hydrate_chunks(
            session, top_chunk_ids, meta_map, retrieval_method="dense_only"
        )

    # Sparse BM25 Search
    bm25_index, chunk_id_list = await get_or_build_bm25_index(session)
    bm25_all = search_bm25(
        bm25_index, chunk_id_list, query_text, top_k=len(chunk_id_list)
    )

    # If filters are provided, filter BM25 candidates to matching chunk_ids
    if chapter_filter or act_filter or section_filter:
        valid_chunk_ids: Set[str] = set()

        # StatuteChunk valid IDs
        filter_stmt = select(StatuteChunk.chunk_id)
        if chapter_filter:
            filter_stmt = filter_stmt.where(StatuteChunk.chapter == chapter_filter)
        if act_filter:
            filter_stmt = filter_stmt.where(
                or_(
                    StatuteChunk.act == act_filter, StatuteChunk.act_short == act_filter
                )
            )
        if section_filter:
            filter_stmt = filter_stmt.where(
                StatuteChunk.section_number == str(section_filter)
            )

        valid_ids_res = await session.execute(filter_stmt)
        valid_chunk_ids.update(valid_ids_res.scalars().all())

        # OffenceClassification valid IDs
        allow_offence = True
        if chapter_filter and chapter_filter not in (
            "FIRST SCHEDULE",
            "THE FIRST SCHEDULE",
            "CLASSIFICATION OF OFFENCES",
            "1",
            "I",
        ):
            allow_offence = False
        if act_filter and act_filter not in (
            "BNS",
            "Bharatiya Nyaya Sanhita, 2023",
            "Bharatiya Nyaya Sanhita",
        ):
            allow_offence = False

        if allow_offence:
            offence_filter_stmt = select(OffenceClassification.id)
            if section_filter:
                offence_filter_stmt = offence_filter_stmt.where(
                    or_(
                        OffenceClassification.bns_section == str(section_filter),
                        OffenceClassification.bns_section.ilike(f"{section_filter}(%)"),
                    )
                )
            res_off = await session.execute(offence_filter_stmt)
            for row_id in res_off.scalars().all():
                valid_chunk_ids.add(f"bns-sched1-{row_id}")

        bm25_results = [(cid, sc) for cid, sc in bm25_all if cid in valid_chunk_ids][
            :candidate_depth
        ]
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
    final_results = await _hydrate_chunks(
        session, top_chunk_ids, fused_meta_map, retrieval_method="hybrid_rrf"
    )
    logger.info("Hybrid search retrieved %d ranked chunks.", len(final_results))
    return final_results


async def search_user_documents(
    session: AsyncSession, session_id: str, query_text: str, top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Performs session-isolated dense vector search strictly within user_document_chunk
    records where session_id matches the current session.

    Returns:
        List of user document chunk dictionaries with source metadata and score.
    """
    if not session_id or not query_text.strip():
        return []

    query_embedding = embed_query(query_text)

    # Cosine distance operator in pgvector is <=>
    # Cosine similarity = 1.0 - distance
    distance_expr = UserDocumentChunk.embedding.cosine_distance(query_embedding).label(
        "distance"
    )
    similarity_expr = (1.0 - distance_expr).label("similarity")

    stmt = (
        select(UserDocumentChunk, UserDocument.filename, similarity_expr)
        .join(UserDocument, UserDocumentChunk.document_id == UserDocument.id)
        .where(
            UserDocumentChunk.session_id == session_id,
            UserDocument.status == "ready",
            UserDocumentChunk.embedding.is_not(None),
        )
        .order_by(distance_expr)
        .limit(top_k)
    )

    res = await session.execute(stmt)
    rows = res.all()

    results = []
    for chunk, filename, similarity in rows:
        sim_val = float(similarity) if similarity is not None else 0.0
        results.append(
            {
                "chunk_id": f"userdoc-{chunk.document_id}-{chunk.chunk_index}",
                "document_id": str(chunk.document_id),
                "session_id": chunk.session_id,
                "filename": filename,
                "page_number": chunk.page_number or 1,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "score": round(sim_val, 4),
                "dense_score": round(sim_val, 4),
                "retrieval_method": "user_document",
                "act": "User Uploaded Document",
                "act_short": "UserDoc",
                "section_number": f"Doc: {filename}",
                "section_title": f"{filename} (Page {chunk.page_number or 1})",
                "page_start": chunk.page_number or 1,
                "page_end": chunk.page_number or 1,
            }
        )

    logger.info(
        "User document search for session '%s' returned %d chunks (top score: %.4f).",
        session_id,
        len(results),
        results[0]["score"] if results else 0.0,
    )
    return results
