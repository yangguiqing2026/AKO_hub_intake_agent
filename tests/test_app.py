"""FastAPI 端点。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in ("ok", "degraded")


def test_metrics() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "sessions_total" in response.json()


def test_session_not_found() -> None:
    response = client.get("/api/v1/intake/sessions/does-not-exist")
    assert response.status_code == 404


def test_review_not_found() -> None:
    response = client.post("/api/v1/intake/review", json={"session_id": "nope", "review_score": 0.5})
    assert response.status_code == 404


def test_ws_intake_roundtrip() -> None:
    with client.websocket_connect("/ws/intake") as websocket:
        websocket.send_json({"type": "intake_input", "text": "修复报价模块的bug，只动校验逻辑，不动数据库"})
        data = websocket.receive_json()
        assert data["status"] in ("DELIVERED", "CLARIFYING")

