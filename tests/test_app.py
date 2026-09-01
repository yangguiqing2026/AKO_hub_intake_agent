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


def test_ws_v2_auth_required() -> None:
    with client.websocket_connect("/ws/intake") as websocket:
        websocket.send_json({"v": 2, "type": "intake_input", "payload": {"text": "修复报价模块的bug，只动校验逻辑，不动数据库"}})
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert data["payload"]["code"] == "AUTH_REQUIRED"


def test_ws_v2_roundtrip() -> None:
    with client.websocket_connect("/ws/intake") as websocket:
        websocket.send_json({"v": 2, "type": "auth", "payload": {"token": "dev-token"}})
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["payload"]["protocol_version"] == 2
        websocket.send_json({"v": 2, "type": "intake_input", "payload": {"text": "修复报价模块的bug，只动校验逻辑，不动数据库"}})
        statuses: list[str] = []
        types: list[str] = []
        for _ in range(8):
            data = websocket.receive_json()
            types.append(str(data["type"]))
            if data["type"] == "status":
                statuses.append(str(data["payload"]["status"]))
            if data["type"] == "wo_preview":
                break
        assert "DELIVERED" in statuses
        assert "wo_preview" in types

