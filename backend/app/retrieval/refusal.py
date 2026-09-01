"""
Refusal detection module for Nyaya Legal Assistant.
Empirically calibrated to refuse out-of-scope and non-legal queries
prior to invoking the LLM generation pipeline.
"""

from typing import Any, Dict, List

from app.core.logging import logger

REFUSAL_MESSAGE = (
    "I don't have enough verified information in the Bharatiya Nagarik "
    "Suraksha Sanhita or the BNS offence schedule to answer this."
)

# Empirically calibrated dense similarity floor from BGE-base-en-v1.5 embeddings
# On-topic cluster: 0.7027 - 0.7896
# Off-topic cluster: 0.4970 - 0.6319
DENSE_SIMILARITY_THRESHOLD = 0.68
RRF_SCORE_FLOOR = 0.030


def should_refuse(
    results: List[Dict[str, Any]],
    dense_threshold: float = DENSE_SIMILARITY_THRESHOLD,
    rrf_floor: float = RRF_SCORE_FLOOR,
) -> bool:
    """
    Determines whether a retrieval result should trigger a refusal:
    1. Deterministic direct section lookups (score=1.0) are NEVER refused.
    2. Empty result sets are ALWAYS refused.
    3. For hybrid retrieval: if top candidate dense cosine similarity < 0.68,
       the query is out of statutory scope and is refused.

    Returns:
        True if the query should be refused without calling the LLM; False otherwise.
    """
    if not results:
        logger.info("Refusal triggered: 0 retrieval results returned.")
        return True

    top_chunk = results[0]

    # Direct section lookup hits bypass refusal threshold
    if top_chunk.get("retrieval_method") == "direct_lookup":
        logger.info(
            "Direct section lookup hit for Section %s -> bypassing refusal threshold.",
            top_chunk.get("section_number"),
        )
        return False

    dense_score = top_chunk.get("dense_score")
    if dense_score is not None:
        if dense_score < dense_threshold:
            logger.info(
                "Refusal triggered: top dense similarity %.4f < threshold %.2f (top chunk %s).",
                dense_score,
                dense_threshold,
                top_chunk.get("chunk_id"),
            )
            return True
        return False

    # Fallback to fused RRF score if dense_score is absent
    fused_score = top_chunk.get("score", 0.0)
    if fused_score < rrf_floor:
        logger.info(
            "Refusal triggered: top RRF score %.6f < floor %.4f.",
            fused_score,
            rrf_floor,
        )
        return True

    return False
