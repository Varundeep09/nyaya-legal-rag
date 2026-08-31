"""
Comprehensive Evaluation Harness for Nyaya Legal Assistant.
Benchmarks the system on the 28-question Golden Set across both 'hybrid'
and 'dense_only' retrieval configurations, measuring Recall@5, Recall@10,
MRR, Citation Accuracy, Refusal Rate, and Latency (p50/p95).
"""

import sys
import os
import json
import time
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
GOLDEN_SET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_set.jsonl")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
COMPARISON_JSON_PATH = os.path.join(RESULTS_DIR, "comparison.json")


def load_golden_set() -> List[Dict[str, Any]]:
    """Loads all benchmark questions from golden_set.jsonl."""
    questions = []
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("{'_comment'") or line.startswith('{"_comment"'):
                continue
            questions.append(json.loads(line))
    return questions


def matches_expected_section(expected_str: str, chunk: Dict[str, Any]) -> bool:
    """
    Checks if a retrieved chunk matches an expected section string like 'BNSS s.35' or 'BNS s.65(1)'.
    """
    m = re.match(r"^(BNSS|BNS)\s+s\.([0-9a-zA-Z\(\)]+)", expected_str.strip(), re.IGNORECASE)
    if not m:
        return False
    exp_act = m.group(1).upper()
    exp_sec = m.group(2).strip().lower()

    chunk_act = str(chunk.get("act_short") or chunk.get("act") or "").strip().upper()
    chunk_sec = str(chunk.get("section_number") or "").strip().lower()

    if exp_act not in chunk_act and ("BNSS" in exp_act and "BHARATIYA NAGARIK" not in chunk_act):
        return False

    if chunk_sec == exp_sec:
        return True

    # Strip sub-sections for base matching (e.g. '35' matches '35(1)' or vice versa)
    base_exp = re.sub(r"\(.*?\)", "", exp_sec).strip()
    base_chunk = re.sub(r"\(.*?\)", "", chunk_sec).strip()

    return base_exp == base_chunk if base_exp else False


def call_search_api(client: httpx.Client, query: str, retrieval_mode: str = "hybrid", top_k: int = 10) -> Tuple[List[Dict[str, Any]], float]:
    """Calls POST /api/v1/search and returns (results, latency_ms)."""
    url = f"{BASE_URL}/api/v1/search"
    payload = {
        "query": query,
        "top_k": top_k,
        "retrieval_mode": retrieval_mode
    }
    t0 = time.perf_counter()
    resp = client.post(url, json=payload, timeout=30.0)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    body = resp.json()
    return body.get("results", []), latency_ms


def call_chat_api(client: httpx.Client, query: str, session_id: str) -> Tuple[Dict[str, Any], float]:
    """Calls POST /api/v1/chat SSE endpoint and parses completion metadata."""
    url = f"{BASE_URL}/api/v1/chat"
    payload = {
        "message": query,
        "session_id": session_id
    }
    t0 = time.perf_counter()
    full_text = ""
    done_data = {}
    sources = []

    with client.stream("POST", url, json=payload, headers={"X-Session-ID": session_id}, timeout=60.0) as resp:
        for line in resp.iter_lines():
            line_str = line.strip()
            if line_str.startswith("data: "):
                raw_json = line_str[6:]
                try:
                    event = json.loads(raw_json)
                    ev_type = event.get("event")
                    ev_data = event.get("data")
                    if ev_type == "token":
                        full_text += ev_data
                    elif ev_type == "sources":
                        sources = ev_data
                    elif ev_type == "done":
                        done_data = ev_data
                except Exception:
                    pass

    latency_ms = (time.perf_counter() - t0) * 1000.0
    done_data["full_text"] = full_text
    done_data["sources"] = sources
    return done_data, latency_ms


def percentile(data: List[float], p: float) -> float:
    """Computes the p-th percentile of a list of floats."""
    if not data:
        return 0.0
    sorted_d = sorted(data)
    idx = (len(sorted_d) - 1) * p
    floor_idx = int(idx)
    ceil_idx = min(floor_idx + 1, len(sorted_d) - 1)
    if floor_idx == ceil_idx:
        return sorted_d[floor_idx]
    return sorted_d[floor_idx] * (ceil_idx - idx) + sorted_d[ceil_idx] * (idx - floor_idx)


def run_evaluation():
    print("=" * 85, flush=True)
    print("           NYAYA LEGAL ASSISTANT — RETRIEVAL & RAG EVALUATION HARNESS          ", flush=True)
    print("=" * 85, flush=True)

    questions = load_golden_set()
    print(f"Loaded {len(questions)} test cases from eval/golden_set.jsonl.", flush=True)
    types_count = {}
    for q in questions:
        types_count[q["type"]] = types_count.get(q["type"], 0) + 1
    print(f"Breakdown: {types_count}\n", flush=True)

    configs = ["hybrid", "dense_only"]
    eval_results = {}

    with httpx.Client() as client:
        for config in configs:
            print("-" * 85, flush=True)
            print(f"  RUNNING BENCHMARK CONFIGURATION: [{config.upper()}]", flush=True)
            print("-" * 85, flush=True)

            q_results = []
            search_latencies = []
            chat_latencies = []

            recall_5_count = 0
            recall_10_count = 0
            reciprocal_ranks = []
            reasoning_citations_valid = 0
            reasoning_count = 0
            refusal_correct = 0
            refusal_count = 0

            for i, item in enumerate(questions, 1):
                q_text = item["q"]
                expected = item.get("expected_sections", [])
                q_type = item["type"]

                # 1. Evaluate Retrieval
                results, search_lat = call_search_api(client, q_text, retrieval_mode=config, top_k=10)
                search_latencies.append(search_lat)

                hit_rank = None
                if expected:
                    for rank, chunk in enumerate(results, 1):
                        if any(matches_expected_section(exp, chunk) for exp in expected):
                            hit_rank = rank
                            break

                r5 = (hit_rank is not None and hit_rank <= 5)
                r10 = (hit_rank is not None and hit_rank <= 10)
                rr = 1.0 / hit_rank if hit_rank else 0.0

                if expected:
                    if r5:
                        recall_5_count += 1
                    if r10:
                        recall_10_count += 1
                    reciprocal_ranks.append(rr)

                # 2. Evaluate Chat / Refusal for reasoning & must_refuse questions
                chat_info = {}
                if q_type == "must_refuse":
                    refusal_count += 1
                    sess_id = f"eval-refuse-{config}-{i}"
                    chat_res, chat_lat = call_chat_api(client, q_text, sess_id)
                    chat_latencies.append(chat_lat)
                    was_refused = chat_res.get("refused", False)
                    if was_refused:
                        refusal_correct += 1
                    chat_info = {"refused": was_refused, "chat_latency_ms": chat_lat}
                    status_str = "REFUSED (OK)" if was_refused else "FAILED TO REFUSE"
                elif q_type == "reasoning":
                    reasoning_count += 1
                    sess_id = f"eval-reason-{config}-{i}"
                    chat_res, chat_lat = call_chat_api(client, q_text, sess_id)
                    chat_latencies.append(chat_lat)
                    stripped = chat_res.get("stripped_hallucinations", [])
                    cits = chat_res.get("citations", [])
                    valid_cits = (len(stripped) == 0 and len(cits) > 0)
                    if valid_cits:
                        reasoning_citations_valid += 1
                    chat_info = {
                        "citations": cits,
                        "stripped": stripped,
                        "citations_valid": valid_cits,
                        "chat_latency_ms": chat_lat
                    }
                    status_str = f"Rank: {hit_rank or 'MISS'} | Cits: {len(cits)} valid"
                else:
                    status_str = f"Rank: {hit_rank or 'MISS'}"

                q_results.append({
                    "index": i,
                    "question": q_text,
                    "type": q_type,
                    "expected": expected,
                    "hit_rank": hit_rank,
                    "recall@5": r5 if expected else None,
                    "recall@10": r10 if expected else None,
                    "rr": rr if expected else None,
                    "search_latency_ms": search_lat,
                    "chat_info": chat_info
                })

                print(f"[{i:02d}/{len(questions):02d}] ({q_type:<11}) {q_text[:46]:<46} -> {status_str} ({search_lat:.1f}ms)", flush=True)

            total_retrieval_qs = len(questions) - refusal_count
            r5_pct = (recall_5_count / total_retrieval_qs * 100.0) if total_retrieval_qs else 0.0
            r10_pct = (recall_10_count / total_retrieval_qs * 100.0) if total_retrieval_qs else 0.0
            mrr = (sum(reciprocal_ranks) / total_retrieval_qs) if total_retrieval_qs else 0.0
            refusal_rate = (refusal_correct / refusal_count * 100.0) if refusal_count else 0.0
            citation_acc = (reasoning_citations_valid / reasoning_count * 100.0) if reasoning_count else 0.0

            eval_results[config] = {
                "recall@5": round(r5_pct, 2),
                "recall@10": round(r10_pct, 2),
                "mrr": round(mrr, 4),
                "refusal_rate": round(refusal_rate, 2),
                "citation_accuracy": round(citation_acc, 2),
                "search_latency_p50_ms": round(percentile(search_latencies, 0.50), 2),
                "search_latency_p95_ms": round(percentile(search_latencies, 0.95), 2),
                "chat_latency_p50_ms": round(percentile(chat_latencies, 0.50), 2) if chat_latencies else 0.0,
                "chat_latency_p95_ms": round(percentile(chat_latencies, 0.95), 2) if chat_latencies else 0.0,
                "details": q_results
            }

    # Save comparison to json
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(COMPARISON_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, indent=2)

    print("\n" + "=" * 85, flush=True)
    print("                    EVALUATION COMPARISON SUMMARY                     ", flush=True)
    print("=" * 85, flush=True)
    print(f"{'Metric':<30} | {'Hybrid (BM25 + Dense + Direct)':<30} | {'Dense Only':<20}", flush=True)
    print("-" * 85, flush=True)
    print(f"{'Recall@5 (%)':<30} | {eval_results['hybrid']['recall@5']:<30.2f} | {eval_results['dense_only']['recall@5']:<20.2f}", flush=True)
    print(f"{'Recall@10 (%)':<30} | {eval_results['hybrid']['recall@10']:<30.2f} | {eval_results['dense_only']['recall@10']:<20.2f}", flush=True)
    print(f"{'Mean Reciprocal Rank (MRR)':<30} | {eval_results['hybrid']['mrr']:<30.4f} | {eval_results['dense_only']['mrr']:<20.4f}", flush=True)
    print(f"{'Must-Refuse Accuracy (%)':<30} | {eval_results['hybrid']['refusal_rate']:<30.2f} | {eval_results['dense_only']['refusal_rate']:<20.2f}", flush=True)
    print(f"{'Citation Accuracy (%)':<30} | {eval_results['hybrid']['citation_accuracy']:<30.2f} | {eval_results['dense_only']['citation_accuracy']:<20.2f}", flush=True)
    print(f"{'Search Latency p50 (ms)':<30} | {eval_results['hybrid']['search_latency_p50_ms']:<30.2f} | {eval_results['dense_only']['search_latency_p50_ms']:<20.2f}", flush=True)
    print(f"{'Search Latency p95 (ms)':<30} | {eval_results['hybrid']['search_latency_p95_ms']:<30.2f} | {eval_results['dense_only']['search_latency_p95_ms']:<20.2f}", flush=True)
    print(f"{'Chat Latency p50 (ms)':<30} | {eval_results['hybrid']['chat_latency_p50_ms']:<30.2f} | {eval_results['dense_only']['chat_latency_p50_ms']:<20.2f}", flush=True)
    print(f"{'Chat Latency p95 (ms)':<30} | {eval_results['hybrid']['chat_latency_p95_ms']:<30.2f} | {eval_results['dense_only']['chat_latency_p95_ms']:<20.2f}", flush=True)
    print("=" * 85, flush=True)
    print(f"Results written to {COMPARISON_JSON_PATH}\n", flush=True)


if __name__ == "__main__":
    run_evaluation()
