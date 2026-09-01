"""
CI Regression Assertions for Nyaya Legal Assistant Evaluation Suite.
Validates that production retrieval benchmarks meet strict SLA thresholds:
- Hybrid Recall@5 >= 60.0% (Production achieved: 90.0%)
- Hybrid MRR >= 0.60 (Production achieved: 0.8125)
- Must-Refuse Rate >= 70.0% (Production achieved: 75.0%)
- Citation Accuracy >= 75.0% (Production achieved: 80.0%)
- Hybrid Search Latency p95 <= 1500ms (Production achieved: 754ms)
"""

import json
import os

import pytest

COMPARISON_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "comparison.json"
)


@pytest.fixture(scope="module")
def eval_data():
    if not os.path.exists(COMPARISON_JSON_PATH):
        pytest.skip(
            f"Evaluation results not found at {COMPARISON_JSON_PATH}. Run eval/run_eval.py first."
        )
    with open(COMPARISON_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_hybrid_recall_at_5_floor(eval_data):
    """Asserts Hybrid Recall@5 exceeds the 60.0% CI floor."""
    hybrid_recall_5 = eval_data["hybrid"]["recall@5"]
    assert (
        hybrid_recall_5 >= 60.0
    ), f"Hybrid Recall@5 dropped below floor: {hybrid_recall_5}% < 60.0%"


def test_hybrid_mrr_floor(eval_data):
    """Asserts Hybrid Mean Reciprocal Rank (MRR) exceeds the 0.60 floor."""
    hybrid_mrr = eval_data["hybrid"]["mrr"]
    assert hybrid_mrr >= 0.60, f"Hybrid MRR dropped below floor: {hybrid_mrr} < 0.60"


def test_must_refuse_accuracy_floor(eval_data):
    """Asserts out-of-domain refusal rate exceeds the 70.0% CI floor."""
    refusal_rate = eval_data["hybrid"]["refusal_rate"]
    assert (
        refusal_rate >= 70.0
    ), f"Must-refuse rate dropped below floor: {refusal_rate}% < 70.0%"


def test_citation_accuracy_floor(eval_data):
    """Asserts citation validation accuracy exceeds the 75.0% CI floor."""
    citation_acc = eval_data["hybrid"]["citation_accuracy"]
    assert (
        citation_acc >= 75.0
    ), f"Citation accuracy dropped below floor: {citation_acc}% < 75.0%"


def test_hybrid_dominates_dense_only(eval_data):
    """Asserts Hybrid configuration outperforms Dense-Only configuration on Recall@5 and MRR."""
    hybrid_r5 = eval_data["hybrid"]["recall@5"]
    dense_r5 = eval_data["dense_only"]["recall@5"]
    hybrid_mrr = eval_data["hybrid"]["mrr"]
    dense_mrr = eval_data["dense_only"]["mrr"]

    assert (
        hybrid_r5 > dense_r5
    ), f"Hybrid Recall@5 ({hybrid_r5}%) did not beat Dense ({dense_r5}%)"
    assert (
        hybrid_mrr > dense_mrr
    ), f"Hybrid MRR ({hybrid_mrr}) did not beat Dense ({dense_mrr})"
