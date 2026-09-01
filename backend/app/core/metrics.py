"""
Prometheus Metrics and LLM Cost Tracking for Nyaya Legal Assistant.
Provides standard Prometheus instrumentation counters, histograms, and cost calculators.
"""

import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response

# 1. HTTP Traffic Metrics
REQUEST_COUNT = Counter(
    "nyaya_http_requests_total",
    "Total count of HTTP requests processed by Nyaya API",
    ["method", "endpoint", "status_code"]
)

REQUEST_DURATION = Histogram(
    "nyaya_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# 2. Retrieval & Embeddings Metrics
RETRIEVAL_DURATION = Histogram(
    "nyaya_retrieval_duration_seconds",
    "Retrieval pipeline execution duration in seconds",
    ["method"],
    buckets=[0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
)

EMBEDDING_DURATION = Histogram(
    "nyaya_embedding_duration_seconds",
    "Dense vector embedding generation duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)

# 3. LLM Observability & Cost Metrics
TOKEN_USAGE = Counter(
    "nyaya_llm_tokens_total",
    "Total tokens consumed across LLM generations",
    ["model", "type"]  # type: "prompt" | "candidate" | "total"
)

LLM_COST_USD = Counter(
    "nyaya_llm_cost_usd_total",
    "Total estimated LLM monetary cost incurred in USD",
    ["model"]
)

QUERY_REFUSALS = Counter(
    "nyaya_query_refusals_total",
    "Total number of queries intercepted and refused by the must-refuse guard"
)

# 4. Ingestion & User Workflows
DOCUMENT_UPLOADS = Counter(
    "nyaya_document_uploads_total",
    "Total user document uploads received",
    ["status"]  # "success" | "rejected" | "corrupt"
)

FEEDBACK_RATINGS = Counter(
    "nyaya_feedback_ratings_total",
    "Total user feedback ratings recorded",
    ["rating"]  # "up" | "down"
)

# 5. Infrastructure Health Gauges
DB_HEALTH_GAUGE = Gauge(
    "nyaya_database_healthy",
    "PostgreSQL + pgvector connection status (1 = Healthy, 0 = Error)"
)

REDIS_HEALTH_GAUGE = Gauge(
    "nyaya_redis_healthy",
    "Redis connection status (1 = Healthy, 0 = Error)"
)


def calculate_gemini_cost(prompt_tokens: int, candidate_tokens: int, model: str = "gemini-3.6-flash") -> float:
    """
    Calculate estimated monetary cost in USD for a Gemini generation.
    Based on official Gemini Flash standard tier pricing:
      - Prompt (Input): $0.075 per 1,000,000 tokens ($0.000075 / 1K tokens)
      - Candidate (Output): $0.300 per 1,000,000 tokens ($0.000300 / 1K tokens)
    """
    input_rate = 0.075 / 1_000_000
    output_rate = 0.300 / 1_000_000
    cost = (prompt_tokens * input_rate) + (candidate_tokens * output_rate)
    return round(cost, 7)


def record_llm_usage(model: str, prompt_tokens: int, candidate_tokens: int):
    """Increment Prometheus token counters and estimated USD cost."""
    TOKEN_USAGE.labels(model=model, type="prompt").inc(prompt_tokens)
    TOKEN_USAGE.labels(model=model, type="candidate").inc(candidate_tokens)
    TOKEN_USAGE.labels(model=model, type="total").inc(prompt_tokens + candidate_tokens)

    cost_usd = calculate_gemini_cost(prompt_tokens, candidate_tokens, model)
    LLM_COST_USD.labels(model=model).inc(cost_usd)
    return cost_usd


async def metrics_endpoint():
    """Exposes Prometheus text formatted metrics for scraping."""
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
