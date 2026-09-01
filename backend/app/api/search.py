"""
Search API router for Nyaya Legal Assistant.
Provides hybrid retrieval and direct section lookup via POST /api/v1/search.
"""

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.logging import logger
from app.retrieval.hybrid_retriever import hybrid_search

router = APIRouter(prefix="", tags=["Search"])


class SearchRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, description="Legal search query or section question"
    )
    top_k: int = Field(
        default=10, ge=1, le=50, description="Number of results to retrieve"
    )
    chapter: Optional[str] = Field(
        default=None, description="Optional Roman numeral chapter filter (e.g. 'XXXV')"
    )
    act: Optional[str] = Field(
        default=None, description="Optional act name or short code filter (e.g. 'BNSS')"
    )
    section: Optional[str] = Field(
        default=None, description="Optional section number filter (e.g. '103')"
    )
    retrieval_mode: Optional[str] = Field(
        default="hybrid",
        description="Retrieval mode: 'hybrid', 'dense_only', or 'bm25_only'",
    )


class SearchResponse(BaseModel):
    query: str
    retrieval_method: str
    results: List[Dict[str, Any]]
    latency_ms: float


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(
    request: SearchRequest, session: AsyncSession = Depends(get_db)
):
    """
    Hybrid Search API endpoint:
    - Automatically identifies direct section lookup queries (e.g. 'what is section 103 bnss')
      and returns deterministic results.
    - Executes dense vector + sparse BM25 retrieval fused with RRF (k=60) for semantic queries.
    - Supports native PostgreSQL metadata filtering by chapter, act, and section.
    - Supports retrieval_mode: 'hybrid' or 'dense_only'.
    """
    start_time = time.perf_counter()
    try:
        results = await hybrid_search(
            session=session,
            query_text=request.query,
            top_k=request.top_k,
            chapter_filter=request.chapter,
            act_filter=request.act,
            section_filter=request.section,
            retrieval_mode=request.retrieval_mode or "hybrid",
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Determine overall retrieval method from results or default
        retrieval_method = results[0]["retrieval_method"] if results else "none"

        return SearchResponse(
            query=request.query,
            retrieval_method=retrieval_method,
            results=results,
            latency_ms=latency_ms,
        )
    except Exception as e:
        logger.error(
            f"Search endpoint error for query '{request.query}': {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing search: {str(e)}",
        )
