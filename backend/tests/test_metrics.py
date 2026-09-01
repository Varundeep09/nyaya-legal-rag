"""
Unit and integration tests for Prometheus metrics and cost calculations.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.metrics import calculate_gemini_cost, record_llm_usage
from app.main import app


def test_calculate_gemini_cost():
    """Verify Gemini Flash monetary cost formula against known token counts."""
    # 1,000,000 prompt tokens ($0.075) + 1,000,000 candidate tokens ($0.300) = $0.375
    cost = calculate_gemini_cost(prompt_tokens=1_000_000, candidate_tokens=1_000_000)
    assert cost == 0.375

    # 1,877 prompt tokens + 1,027 candidate tokens
    cost_single_query = calculate_gemini_cost(prompt_tokens=1877, candidate_tokens=1027)
    # (1877 * 0.075 / 1e6) + (1027 * 0.30 / 1e6) = 0.000140775 + 0.0003081 = 0.000448875
    assert 0.00044 <= cost_single_query <= 0.00046


def test_record_llm_usage():
    """Verify record_llm_usage increments Prometheus counters without errors."""
    cost = record_llm_usage(
        model="gemini-3.6-flash", prompt_tokens=500, candidate_tokens=250
    )
    assert cost > 0.0


@pytest.mark.asyncio
async def test_get_metrics_endpoint():
    """Verify GET /api/v1/metrics returns 200 OK with Prometheus exposition format."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/metrics")
        assert response.status_code == 200
        text = response.text
        assert "nyaya_http_requests_total" in text
        assert "nyaya_llm_tokens_total" in text
        assert "nyaya_database_healthy" in text
