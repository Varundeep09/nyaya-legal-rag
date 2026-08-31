"""
Direct section lookup module for deterministic retrieval by section number.
Bypasses hybrid similarity search when queries explicitly target a section.
Supports dual-table routing across BNSS statute chunks and BNS First Schedule offences.
"""

import re
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.core.models import StatuteChunk, OffenceClassification
from app.core.logging import logger


def detect_act_and_section_intent(query: str) -> Optional[Dict[str, str]]:
    """
    Identifies target act and section identifier from query.
    Distinguishes explicit BNS vs BNSS references:
      - 'what is BNS section 64(2)' -> {'section': '64(2)', 'base_section': '64', 'act': 'BNS'}
      - 'what is section 103 bnss' -> {'section': '103', 'base_section': '103', 'act': 'BNSS'}
      - 'section 103' -> {'section': '103', 'base_section': '103', 'act': 'AMBIGUOUS'}
    """
    if not query:
        return None

    q = query.strip().lower()

    # Check act explicitly mentioned
    is_bnss = bool(re.search(r"\bbnss\b|\bbharatiya\s+nagarik\s+suraksha\b", q))
    is_bns = bool(re.search(r"\bbns\b|\bbharatiya\s+nyaya\b", q)) and not is_bnss

    # Pattern with section number and optional subsection (e.g., 64(2), 65(1), 103, 103(1))
    p = re.compile(
        r"(?:(?:what\s+(?:is|does)\s+)?(?:the\s+)?(?:bns\s+|bnss\s+)?(?:section|sec\.?|s\.?)\s*(\d{1,3}(?:\([0-9a-z]+\)){0,2})|"
        r"\b(?:bnss|bns)\s*(?:section|sec\.?|s\.?)?\s*(\d{1,3}(?:\([0-9a-z]+\)){0,2})|"
        r"\b(?:section|sec\.?|s\.?)\s*(\d{1,3}(?:\([0-9a-z]+\)){0,2}))",
        re.IGNORECASE
    )

    m = p.search(q)
    if not m:
        return None

    raw_sec = m.group(1) or m.group(2) or m.group(3)
    if not raw_sec:
        return None

    has_sub = "(" in raw_sec
    base_sec_match = re.match(r"^(\d+)", raw_sec)
    base_sec = base_sec_match.group(1) if base_sec_match else raw_sec

    if is_bns:
        act = "BNS"
    elif is_bnss:
        act = "BNSS"
    else:
        act = "AMBIGUOUS"

    return {
        "section": raw_sec,
        "base_section": base_sec,
        "act": act
    }


def detect_section_intent(query: str) -> Optional[str]:
    """
    Regex-based detector for direct section lookup intents.
    Extracts the section identifier from explicit queries such as:
      - 'what is section 103 bnss' -> '103'
      - 'section 103' -> '103'
      - 'BNSS s.103' -> '103'
      - 'what is BNS section 64(2)' -> '64(2)'
      - 'explain section 103(1)' -> '103'
    """
    intent = detect_act_and_section_intent(query)
    if not intent:
        return None

    # If query explicitly targets BNS, return full section identifier (e.g. '64(2)', '65(1)')
    if intent["act"] == "BNS":
        return intent["section"]

    # For BNSS and general ambiguous section queries, return base section number
    return intent["base_section"]


async def fetch_section_directly(
    session: AsyncSession,
    section_number: str
) -> List[Dict[str, Any]]:
    """
    Fetches all statute_chunk rows for a given section_number directly from PostgreSQL (BNSS).
    Ordered deterministically by chunk_id. Bypasses vector & BM25 search.
    """
    logger.info("Performing deterministic direct lookup for Section %s (BNSS)...", section_number)
    stmt = (
        select(StatuteChunk)
        .where(StatuteChunk.section_number == str(section_number))
        .order_by(StatuteChunk.chunk_id)
    )
    result = await session.execute(stmt)
    chunks = result.scalars().all()

    if not chunks:
        logger.warning("Direct BNSS section lookup found 0 chunks for Section %s.", section_number)
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


async def fetch_bns_offence_directly(
    session: AsyncSession,
    bns_section: str
) -> List[Dict[str, Any]]:
    """
    Fetches matching offence_classification rows directly from PostgreSQL (BNS First Schedule).
    Ordered deterministically by page_number, id. Bypasses vector & BM25 search.
    """
    logger.info("Performing deterministic direct lookup for BNS Section %s (First Schedule)...", bns_section)
    clean_sec = re.sub(r'\s+', '', bns_section)
    
    stmt = (
        select(OffenceClassification)
        .where(
            or_(
                OffenceClassification.bns_section == clean_sec,
                OffenceClassification.bns_section.ilike(f"{clean_sec}(%)")
            )
        )
        .order_by(OffenceClassification.page_number, OffenceClassification.id)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        logger.warning("Direct BNS offence lookup found 0 rows for Section %s.", bns_section)
        return []

    results = []
    for row in rows:
        results.append({
            "chunk_id": f"bns-sched1-s{row.bns_section}",
            "act": "Bharatiya Nyaya Sanhita, 2023",
            "act_short": "BNS",
            "chapter": "FIRST SCHEDULE",
            "chapter_title": "CLASSIFICATION OF OFFENCES",
            "section_number": row.bns_section,
            "section_title": f"BNS Section {row.bns_section}",
            "subsection": None,
            "clause": None,
            "text": f"BNS Section {row.bns_section}: {row.offence_description}\nClassification: {row.cognizable or 'N/A'}, {row.bailable or 'N/A'}, Triable by: {row.triable_court or 'N/A'}",
            "page_start": row.page_number,
            "page_end": row.page_number,
            "has_proviso": False,
            "has_illustration": False,
            "has_exception": False,
            "references_json": [],
            "retrieval_method": "direct_lookup",
            "score": 1.0,
            "cognizable": row.cognizable,
            "bailable": row.bailable,
            "triable_court": row.triable_court,
            "punishment": row.punishment,
            "dense_score": None,
            "dense_rank": None,
            "bm25_score": None,
            "bm25_rank": None
        })

    logger.info("Direct BNS offence lookup returned %d rows for Section %s.", len(results), bns_section)
    return results
