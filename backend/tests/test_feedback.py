"""
Unit and integration tests for POST /api/v1/feedback endpoint.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_submit_feedback_valid():
    """Verify submitting valid feedback returns 201 Created and persisted ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "session_id": "test-feedback-session-1",
            "rating": "up",
            "comment": "Section 35 arrest conditions were explained accurately."
        }
        response = await ac.post("/api/v1/feedback", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["session_id"] == "test-feedback-session-1"
        assert data["rating"] == "up"
        assert data["status"] == "recorded"
        assert data["comment"] == "Section 35 arrest conditions were explained accurately."


@pytest.mark.asyncio
async def test_submit_feedback_invalid_rating():
    """Verify submitting an invalid rating value returns 422 Unprocessable Entity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "session_id": "test-feedback-session-2",
            "rating": "neutral",
            "comment": "Average answer"
        }
        response = await ac.post("/api/v1/feedback", json=payload)
        assert response.status_code == 422
