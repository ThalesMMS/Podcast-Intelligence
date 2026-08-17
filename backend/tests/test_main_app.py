from __future__ import annotations

from fastapi.testclient import TestClient

from podcast_intelligence.main import app


def test_health_and_metrics_routes_with_upgraded_asgi_stack() -> None:
    client = TestClient(app)
    try:
        health = client.get("/health/live")
        metrics = client.get("/metrics")
    finally:
        client.close()

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.text
