"""
Tests for dense embedding generation with BAAI/bge-base-en-v1.5.
Verifies model dimensions, determinism, asymmetric prefix divergence, and L2 normalization.
"""

import pytest
import math
from app.retrieval.embeddings import (
    get_embedding_model,
    embed_passages,
    embed_query,
    check_token_length,
    EXPECTED_DIMENSION
)


def test_embedding_model_properties():
    """Verify real loaded model properties: max_seq_length=512 and embedding_dimension=768."""
    model = get_embedding_model()
    assert model.max_seq_length == 512
    assert model.get_sentence_embedding_dimension() == EXPECTED_DIMENSION


def test_embedding_determinism():
    """Verify that embedding the same text twice produces bitwise identical float vectors."""
    text = "Section 35. When police may arrest without warrant."
    vec1 = embed_passages([text])[0]
    vec2 = embed_passages([text])[0]

    assert len(vec1) == EXPECTED_DIMENSION
    assert len(vec2) == EXPECTED_DIMENSION
    assert vec1 == vec2, "Embeddings for identical text must be deterministic"


def test_asymmetric_prefix_divergence():
    """
    Verify that embed_query ('query: ...') and embed_passages ('passage: ...')
    for the exact same underlying text produce DIFFERENT vectors due to bge prefixing.
    """
    text = "Procedure when investigation cannot be completed in twenty-four hours."
    query_vec = embed_query(text)
    passage_vec = embed_passages([text])[0]

    assert len(query_vec) == EXPECTED_DIMENSION
    assert len(passage_vec) == EXPECTED_DIMENSION
    assert query_vec != passage_vec, "Query and passage vectors must diverge due to asymmetric prefixes"

    # Verify cosine similarity is high but strictly < 1.0
    dot_product = sum(q * p for q, p in zip(query_vec, passage_vec))
    assert 0.70 < dot_product < 0.999, f"Expected high semantic similarity with prefix divergence, got {dot_product}"


def test_l2_normalization():
    """Verify that both passage and query embeddings have L2 unit norm (magnitude ~ 1.0)."""
    text = "Bail in case of non-bailable offence."
    passage_vec = embed_passages([text])[0]
    query_vec = embed_query(text)

    passage_norm = math.sqrt(sum(x * x for x in passage_vec))
    query_norm = math.sqrt(sum(x * x for x in query_vec))

    assert math.isclose(passage_norm, 1.0, rel_tol=1e-4), f"Passage vector norm should be 1.0, got {passage_norm}"
    assert math.isclose(query_norm, 1.0, rel_tol=1e-4), f"Query vector norm should be 1.0, got {query_norm}"


def test_token_length_check():
    """Verify token length checker accurately counts tokens and flags over-limit text."""
    short_text = "Short section preamble."
    is_exceeded, count = check_token_length(short_text)
    assert not is_exceeded
    assert 1 < count < 50

    # Synthetic text of 600 repeated legal words (> 512 tokens)
    long_text = "cognizable offence warrant magistrate arrest " * 150
    is_exceeded_long, count_long = check_token_length(long_text)
    assert is_exceeded_long
    assert count_long > 512
