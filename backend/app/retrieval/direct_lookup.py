"""
Direct section lookup module for deterministic retrieval by section number.
Bypasses hybrid similarity search when queries explicitly target a section.
"""

import re
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.models import StatuteChunk
from app.core.logging import logger


def detect_section_intent(query: str) -> Optional[str]:
    """
    Regex-based detector for direct section lookup intents.
    Extracts the section number from explicit queries such as:
      - 'what is section 103 bnss' -> '103'
      - 'section 103' -> '103'
      - 'BNSS s.103' -> '103'
      - 'BNSS 103' -> '103'
      - 's 103' -> '103'
      - 'what does section 103 say' -> '103'
      - 'explain section 103(1)' -> '103'

    Returns None for general semantic queries like 'how many police officers are needed'
    where no section identifier cue is present.
    """
    if not query:
        return None

    q = query.strip().lower()

    # Pattern 1: Leading question phrases or verbs followed by section/s./sec. + number + optional subsection
    # e.g. "what is section 103 bnss", "what does section 103 say", "explain section 103(1)"
    p1 = re.compile(
        r"^(?:what\s+(?:is|does)\s+)?(?:the\s+)?(?:section|sec\.?|s\.?)\s*(\d{1,3})(?:\([a-zA-Z0-9]+\))?(?:\s+(?:of\s+)?(?:the\s+)?(?:bnss|bns|act))?.*$",
        re.IGNORECASE
    )
    m1 = p1.match(q)
    if m1:
        return m1.group(1)

    # Pattern 2: Act name prefix followed by section cue or bare number
    # e.g. "BNSS s.103", "BNSS 103", "BNSS section 103"
    p2 = re.compile(
        r"^\b(?:bnss|bns)\s*(?:section|sec\.?|s\.?)?\s*(\d{1,3})(?:\([a-zA-Z0-9]+\))?.*$",
        re.IGNORECASE
    )
    m2 = p2.match(q)
    if m2:
        return m2.group(1)

    # Pattern 3: Standalone section reference e.g. "section 103", "s 103", "sec. 103", "s.103"
    p3 = re.compile(
        r"^\b(?:section|sec\.?|s\.?)\s*(\d{1,3})(?:\([a-zA-Z0-9]+\))?.*$",
        re.IGNORECASE
    )
    m3 = p3.match(q)
    if m3:
        return m3.group(1)

    # Pattern 4: Embedded section queries e.g. "tell me about section 103", "details of sec 103"
    p4 = re.compile(
        r"\b(?:section|sec\.?|s\.?)\s*(\d{1,3})\b",
        re.IGNORECASE
    )
    m4 = p4.search(q)
    if m4:
        return m4.group(1)

    return None


async def fetch_section_directly(
    session: AsyncSession,
    section_number: str
) -> List[Dict[str, Any]]:
    """
    Fetches all statute_chunk rows for a given section_number directly from PostgreSQL,
    ordered deterministically by chunk_id. Bypasses vector & BM25 search.
    
    Returns:
        List of dicts representing the statute chunks with retrieval_method='direct_lookup'.
    """
    logger.info("Performing deterministic direct lookup for Section %s...", section_number)
    stmt = (
        select(StatuteChunk)
        .where(StatuteChunk.section_number == str(section_number))
        .order_by(StatuteChunk.chunk_id)
    )
    result = await session.execute(stmt)
    chunks = result.scalars().all()

    if not chunks:
        logger.warning("Direct section lookup found 0 chunks for Section %s.", section_number)
        return []

    results = []
    for chunk in chunks:
        results.append({
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
            "retrieval_method": "direct_lookup",
            "score": 1.0,
            "dense_score": None,
            "dense_rank": None,
            "bm25_score": None,
            "bm25_rank": None
        })

    logger.info("Direct lookup returned %d chunks for Section %s.", len(results), section_number)
    return results
