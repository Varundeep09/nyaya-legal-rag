"""
Unit and integration tests for First Schedule (BNS Offence Classification) parser and routing.
"""

import pytest

from app.ingestion.bns_chunker import extract_pages
from app.ingestion.schedule_parser import parse_first_schedule
from app.retrieval.direct_lookup import (
    detect_act_and_section_intent,
)
from app.retrieval.hybrid_retriever import hybrid_search


def test_row_boundary_detection():
    """
    Parses pages 158-165 and asserts bns_section '64(2)' and '65(1)' both exist
    as separate distinct rows without merging.
    """
    pages_data = extract_pages(
        "data/raw/bns_bare_act_2023.pdf", start_page=158, end_page=165
    )
    records = parse_first_schedule(pages_data)

    sections = [r["bns_section"] for r in records]
    assert "64(2)" in sections, "Expected bns_section '64(2)' in parsed schedule"
    assert "65(1)" in sections, "Expected bns_section '65(1)' in parsed schedule"

    # Ensure 64(2) and 65(1) are distinct items
    idx_64_2 = sections.index("64(2)")
    idx_65_1 = sections.index("65(1)")
    assert idx_64_2 != idx_65_1, "64(2) and 65(1) must not be merged into the same row"


def test_tail_extraction_known_row():
    """
    Asserts known ground truth row 64(2) matches exact classification fields:
      - cognizable: 'Cognizable'
      - bailable: 'Non-bailable'
      - triable_court: 'Court of Session'
    """
    pages_data = extract_pages(
        "data/raw/bns_bare_act_2023.pdf", start_page=158, end_page=165
    )
    records = parse_first_schedule(pages_data)

    row_64_2 = next((r for r in records if r["bns_section"] == "64(2)"), None)
    assert row_64_2 is not None, "Row 64(2) must be present"
    assert "Cognizable" in row_64_2["cognizable"]
    assert "Non-bailable" in row_64_2["bailable"]
    assert "Court of Session" in row_64_2["triable_court"]
    assert row_64_2["needs_review"] is False

    row_65_1 = next((r for r in records if r["bns_section"] == "65(1)"), None)
    assert row_65_1 is not None, "Row 65(1) must be present"
    assert "Cognizable" in row_65_1["cognizable"]
    assert "Non-bailable" in row_65_1["bailable"]
    assert "Court of Session" in row_65_1["triable_court"]
    assert row_65_1["needs_review"] is False


def test_needs_review_flagged_when_tail_ambiguous():
    """
    Verifies that rows with multi-line wrapped or ambiguous tail fields
    are flagged with needs_review=True rather than hallucinated or corrupt values.
    """
    pages_data = extract_pages(
        "data/raw/bns_bare_act_2023.pdf", start_page=158, end_page=189
    )
    records = parse_first_schedule(pages_data)

    flagged = [r for r in records if r["needs_review"]]
    assert (
        len(flagged) > 0
    ), f"Expected at least 1 row flagged with needs_review=True, got {len(flagged)}"

    # E.g., Section 49 whose court text wraps across lines
    row_49 = next((r for r in records if r["bns_section"] == "49"), None)
    assert row_49 is not None
    assert row_49["needs_review"] is True


def test_bns_intent_detection():
    """
    Asserts detect_act_and_section_intent accurately differentiates BNS vs BNSS.
    """
    bns_intent = detect_act_and_section_intent("what is BNS section 65(1)")
    assert bns_intent is not None
    assert bns_intent["act"] == "BNS"
    assert bns_intent["section"] == "65(1)"

    bnss_intent = detect_act_and_section_intent("what is section 103 bnss")
    assert bnss_intent is not None
    assert bnss_intent["act"] == "BNSS"
    assert bnss_intent["base_section"] == "103"


@pytest.mark.asyncio
async def test_bns_direct_lookup_live_routing(test_session):
    """
    Calls hybrid_search with 'what is BNS section 65(1)' and asserts it routes
    to offence_classification returning the rape-under-sixteen row.
    """
    results = await hybrid_search(test_session, "what is BNS section 65(1)", top_k=5)
    assert len(results) >= 1
    top = results[0]
    assert top["section_number"] == "65(1)"
    assert top["act_short"] == "BNS"
    assert top["cognizable"] == "Cognizable"
    assert top["bailable"] == "Non-bailable"
    assert top["triable_court"] == "Court of Session"
    assert "sixteen" in top["text"].lower()
