"""
Unit tests for the post-generation citation validation guard.
"""

from app.llm.citation_guard import (
    extract_citations,
    validate_citations,
    sanitize_response
)


def test_citation_extraction():
    """
    Asserts regex correctly extracts all BNSS and BNS citations from response text.
    """
    text = (
        "Under [BNSS s.35(1)], a police officer may arrest without a warrant. "
        "For rape of a minor under sixteen, punishment is under [BNS s.65(1)]."
    )
    citations = extract_citations(text)
    assert "35(1)" in citations
    assert "65(1)" in citations
    assert len(citations) == 2


def test_citation_validation_valid_and_hallucinated():
    """
    Constructs generated_text with one valid citation matching retrieved chunks
    and one fabricated citation ([BNSS s.999]), asserting validate_citations
    correctly splits them into valid and hallucinated lists.
    """
    retrieved_chunks = [
        {
            "chunk_id": "bnss-s35-001",
            "act_short": "BNSS",
            "section_number": "35",
            "section_title": "Section 35"
        },
        {
            "chunk_id": "bns-sched1-s65(1)",
            "act_short": "BNS",
            "section_number": "65(1)",
            "section_title": "BNS Section 65(1)"
        }
    ]

    generated_text = (
        "A police officer may arrest without warrant in cognizable cases [BNSS s.35]. "
        "Furthermore, special search powers apply [BNSS s.999]."
    )

    citations = extract_citations(generated_text)
    valid, hallucinated = validate_citations(citations, retrieved_chunks)

    assert "35" in valid
    assert "999" in hallucinated
    assert len(valid) == 1
    assert len(hallucinated) == 1


def test_sanitize_response_strips_hallucinated_citations():
    """
    Verifies that sanitize_response strips fabricated citations while
    preserving valid inline citations.
    """
    retrieved_chunks = [
        {
            "chunk_id": "bnss-s103-001",
            "act_short": "BNSS",
            "section_number": "103",
            "section_title": "Section 103"
        }
    ]

    text = (
        "Search procedures are defined in [BNSS s.103]. "
        "Unauthorized entry is penalized under [BNSS s.888]."
    )

    sanitized, valid, hallucinated = sanitize_response(
        text,
        retrieved_chunks,
        query="search procedures"
    )

    assert "[BNSS s.103]" in sanitized
    assert "[BNSS s.888]" not in sanitized
    assert "103" in valid
    assert "888" in hallucinated
