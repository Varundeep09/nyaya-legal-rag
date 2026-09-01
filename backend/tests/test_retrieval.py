"""
Real integration and unit tests for hybrid retrieval, BM25 indexing, direct section lookup,
and Reciprocal Rank Fusion against live PostgreSQL + pgvector data.
"""

import pytest

from app.retrieval.direct_lookup import detect_section_intent
from app.retrieval.hybrid_retriever import hybrid_search, reciprocal_rank_fusion


def test_direct_lookup_detects_section_query():
    """
    Asserts detect_section_intent correctly extracts '103' from all real phrasings
    and returns None for general semantic queries.
    """
    valid_queries = [
        "what is section 103 bnss",
        "section 103",
        "BNSS s.103",
        "BNSS 103",
        "s 103",
        "what does section 103 say",
        "explain section 103(1)",
    ]
    for q in valid_queries:
        sec = detect_section_intent(q)
        assert sec == "103", f"Expected '103' for query '{q}', got {sec}"

    # Must NOT false-positive on general questions
    negative_queries = [
        "how many police officers are needed",
        "can a police officer arrest someone without a warrant",
        "bail conditions for bailable offence",
    ]
    for nq in negative_queries:
        res = detect_section_intent(nq)
        assert res is None, f"Expected None for non-section query '{nq}', got {res}"


@pytest.mark.asyncio
async def test_direct_lookup_returns_correct_section(test_session):
    """
    Calls hybrid_search with 'section 35 bnss' and asserts that every returned result
    has section_number=='35' and retrieval_method=='direct_lookup'.
    """
    results = await hybrid_search(test_session, "section 35 bnss", top_k=10)

    assert len(results) >= 1, "Expected results for section 35 direct lookup"
    for r in results:
        assert (
            r["section_number"] == "35"
        ), f"Expected section 35, got {r['section_number']}"
        assert (
            r["retrieval_method"] == "direct_lookup"
        ), f"Expected direct_lookup, got {r['retrieval_method']}"
        assert r["score"] == 1.0


@pytest.mark.asyncio
async def test_hybrid_search_finds_relevant_section(test_session):
    """
    Calls hybrid_search with 'arrest without warrant police officer' and asserts
    that Section 35 ('When police may arrest without warrant') appears in the top 10 results.
    """
    results = await hybrid_search(
        test_session, "arrest without warrant police officer", top_k=10
    )

    assert len(results) > 0, "Expected results for hybrid search"
    top_sections = [r["section_number"] for r in results]
    print(f"\n[Test Result] Top 10 retrieved section numbers: {top_sections}")

    assert (
        "35" in top_sections
    ), f"Expected Section 35 in top 10 results, but got: {top_sections}"
    assert results[0]["retrieval_method"] == "hybrid_rrf"


@pytest.mark.asyncio
async def test_chapter_filter_is_enforced(test_session):
    """
    Calls hybrid_search with a chapter filter ('XXXV' - Bail and Bonds)
    and asserts 100% of returned results match chapter=='XXXV'.
    """
    results = await hybrid_search(
        test_session, "bail conditions", chapter_filter="XXXV", top_k=5
    )

    assert len(results) >= 1, "Expected results for chapter XXXV search"
    for r in results:
        assert (
            r["chapter"] == "XXXV"
        ), f"Expected chapter XXXV, got {r['chapter']} for chunk {r['chunk_id']}"


def test_rrf_fusion_math():
    """
    Unit test for reciprocal_rank_fusion verifying mathematical correctness of RRF scores:
    score(d) = sum(1 / (k + rank_m(d))) with k=60.
    """
    dense_results = [
        ("doc_A", 0.95),  # dense rank 1
        ("doc_B", 0.85),  # dense rank 2
        ("doc_C", 0.75),  # dense rank 3
    ]
    bm25_results = [
        ("doc_B", 18.0),  # bm25 rank 1
        ("doc_D", 14.0),  # bm25 rank 2
        ("doc_A", 10.0),  # bm25 rank 3
    ]

    k = 60
    # Expected calculations:
    # doc_A: dense_rank=1, bm25_rank=3 -> 1/(60+1) + 1/(60+3) = 1/61 + 1/63 = 0.01639344 + 0.01587301 = 0.03226645
    # doc_B: dense_rank=2, bm25_rank=1 -> 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.01612903 + 0.01639344 = 0.03252247
    # doc_C: dense_rank=3, bm25_rank=None -> 1/(60+3) = 1/63 = 0.01587301
    # doc_D: dense_rank=None, bm25_rank=2 -> 1/(60+2) = 1/62 = 0.01612903

    expected_score_b = (1.0 / 62) + (1.0 / 61)
    expected_score_a = (1.0 / 61) + (1.0 / 63)
    expected_score_d = 1.0 / 62
    expected_score_c = 1.0 / 63

    fused = reciprocal_rank_fusion(dense_results, bm25_results, k=k)

    # Assert correct ordering: B > A > D > C
    assert len(fused) == 4
    assert fused[0]["chunk_id"] == "doc_B"
    assert pytest.approx(fused[0]["rrf_score"], rel=1e-5) == expected_score_b
    assert fused[0]["dense_rank"] == 2
    assert fused[0]["bm25_rank"] == 1

    assert fused[1]["chunk_id"] == "doc_A"
    assert pytest.approx(fused[1]["rrf_score"], rel=1e-5) == expected_score_a
    assert fused[1]["dense_rank"] == 1
    assert fused[1]["bm25_rank"] == 3

    assert fused[2]["chunk_id"] == "doc_D"
    assert pytest.approx(fused[2]["rrf_score"], rel=1e-5) == expected_score_d

    assert fused[3]["chunk_id"] == "doc_C"
    assert pytest.approx(fused[3]["rrf_score"], rel=1e-5) == expected_score_c


def test_non_corpus_statute_gating_regression():
    """
    Regression test for non-corpus statute direct lookup leak.
    Asserts non-corpus statute queries (Income Tax Act, Contract Act) return None
    from intent detection and trigger should_refuse == True.
    Asserts BNSS, BNS, and ambiguous queries retain correct intent detection.
    """
    from app.retrieval.direct_lookup import detect_act_and_section_intent
    from app.retrieval.refusal import should_refuse

    # 1. Non-corpus statute queries MUST return None and trigger refusal
    q1 = "What is section 80C of the Income Tax Act?"
    assert detect_act_and_section_intent(q1) is None
    assert should_refuse([], query_text=q1) is True

    q2 = "Explain section 420 of the Indian Contract Act."
    assert detect_act_and_section_intent(q2) is None
    assert should_refuse([], query_text=q2) is True

    # 2. Corpus BNSS query MUST return BNSS intent and NOT refuse
    q3 = "What does section 35 of BNSS provide?"
    intent3 = detect_act_and_section_intent(q3)
    assert intent3 is not None
    assert intent3["act"] == "BNSS"
    assert intent3["base_section"] == "35"

    # 3. Corpus BNS query MUST return BNS intent
    q4 = "What does section 65 of BNS mean?"
    intent4 = detect_act_and_section_intent(q4)
    assert intent4 is not None
    assert intent4["act"] == "BNS"
    assert intent4["base_section"] == "65"

    # 4. Bare section query MUST return AMBIGUOUS intent
    q5 = "Tell me about section 35."
    intent5 = detect_act_and_section_intent(q5)
    assert intent5 is not None
    assert intent5["act"] == "AMBIGUOUS"
    assert intent5["base_section"] == "35"
