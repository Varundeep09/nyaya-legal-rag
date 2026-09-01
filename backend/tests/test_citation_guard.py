"""
Unit tests for the post-generation citation validation guard covering
statute section citations ([BNSS s.X], [BNS s.X]) and user document citations ([Doc: filename, p.X]).
"""

from app.llm.citation_guard import (
    extract_citations,
    extract_doc_citations,
    sanitize_response,
    validate_citations,
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
            "section_title": "Section 35",
        },
        {
            "chunk_id": "bns-sched1-s65(1)",
            "act_short": "BNS",
            "section_number": "65(1)",
            "section_title": "BNS Section 65(1)",
        },
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
            "section_title": "Section 103",
        }
    ]

    text = (
        "Search procedures are defined in [BNSS s.103]. "
        "Unauthorized entry is penalized under [BNSS s.888]."
    )

    sanitized, valid, hallucinated = sanitize_response(
        text, retrieved_chunks, query="search procedures"
    )

    assert "[BNSS s.103]" in sanitized
    assert "[BNSS s.888]" not in sanitized
    assert "103" in valid
    assert "888" in hallucinated


def test_doc_citation_extraction():
    """
    Asserts regex correctly extracts (filename, page_number) tuples from document citations.
    """
    text = (
        "According to the FIR [Doc: police_fir.pdf, p.2], the accused fled. "
        "As noted in the agreement [Doc: lease_contract.pdf]."
    )
    doc_cits = extract_doc_citations(text)
    assert ("police_fir.pdf", 2) in doc_cits
    assert ("lease_contract.pdf", None) in doc_cits
    assert len(doc_cits) == 2


def test_doc_citation_validation():
    """
    Tests validate_doc_citations and sanitize_response on user document citations:
    - [Doc: tenant_notice.pdf, p.1] -> VALID (matches retrieved user chunk)
    - [Doc: fake_judgment.pdf, p.3] -> INVALID (file was never retrieved)
    - [Doc: tenant_notice.pdf, p.99] -> INVALID (page 99 was not in retrieved chunks)
    """
    retrieved_chunks = [
        {
            "chunk_id": "userdoc-1-0",
            "retrieval_method": "user_document",
            "filename": "tenant_notice.pdf",
            "page_number": 1,
            "text": "Notice of eviction.",
        },
        {
            "chunk_id": "bnss-s35-001",
            "act_short": "BNSS",
            "section_number": "35",
            "section_title": "Section 35",
        },
    ]

    generated_text = (
        "The tenant is in arrears of Rs 1,80,000 [Doc: tenant_notice.pdf, p.1]. "
        "The High Court issued stay in [Doc: fake_judgment.pdf, p.3]. "
        "Further lease terms are in [Doc: tenant_notice.pdf, p.99]. "
        "Police action follows [BNSS s.35]."
    )

    sanitized, valid, hallucinated = sanitize_response(
        generated_text, retrieved_chunks, query="arrears and eviction"
    )

    # Valid citations preserved
    assert "[Doc: tenant_notice.pdf, p.1]" in sanitized
    assert "[BNSS s.35]" in sanitized
    assert "Doc: tenant_notice.pdf, p.1" in valid
    assert "35" in valid

    # Hallucinated citations stripped
    assert "[Doc: fake_judgment.pdf, p.3]" not in sanitized
    assert "[Doc: tenant_notice.pdf, p.99]" not in sanitized
    assert "Doc: fake_judgment.pdf, p.3" in hallucinated
    assert "Doc: tenant_notice.pdf, p.99" in hallucinated
