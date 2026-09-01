"""FastAPI 端点。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app as app_module
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


def test_metrics_includes_budget_and_queue() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "budget" in body
    assert "usage_percent" in body["budget"]
    assert "queue" in body


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


def test_bootstrap_shape() -> None:
    response = client.get("/api/v1/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "AKO_hub_intake_agent"
    assert body["ws"]["auth_timeout_seconds"] > 0
    assert "terms" in body


def test_sessions_list_and_create() -> None:
    created = client.post("/api/v1/intake/sessions", json={})
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    listing = client.get("/api/v1/intake/sessions")
    assert listing.status_code == 200
    assert any(s["session_id"] == session_id for s in listing.json()["sessions"])


def test_create_session_expert_mode() -> None:
    draft = {
        "module": "AKO_quote_agent", "action": "审计", "scope": "只动报价校验",
        "rules": ["不修改生产环境"], "prohibitions": ["禁止直接修改生产数据库"],
        "deliverable": "输出审计报告", "deadline": "90分钟",
    }
    response = client.post("/api/v1/intake/sessions", json={"draft_wo": draft})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REVIEWING"
    assert body["review_record"]["structural_passed"] is True


def test_create_session_expert_mode_missing_fields_400() -> None:
    """专家模式 draft 缺必填字段 → 400 schema_error（修复轮 1 覆盖）。"""
    response = client.post("/api/v1/intake/sessions", json={"draft_wo": {"action": "审计"}})
    assert response.status_code == 400
    assert "schema_error" in response.json()["detail"]


def test_abandon_session() -> None:
    created = client.post("/api/v1/intake/sessions", json={}).json()
    response = client.post(f"/api/v1/intake/sessions/{created['session_id']}/abandon")
    assert response.status_code == 200
    assert response.json()["status"] == "ABANDONED"
    missing = client.post("/api/v1/intake/sessions/nope/abandon")
    assert missing.status_code == 404


def test_queue_stats_and_flush() -> None:
    stats = client.get("/api/v1/intake/queue/stats")
    assert stats.status_code == 200
    assert "pending" in stats.json()
    flushed = client.post("/api/v1/intake/queue/flush")
    assert flushed.status_code == 200
    assert "flushed" in flushed.json()


def test_identity_login_dev_mode() -> None:
    response = client.post("/api/v1/identity/login", json={"account": "a", "fingerprint": "123456"})
    assert response.status_code == 200
    assert response.json()["token"] == "dev-token"


def test_identity_verify_dev_mode() -> None:
    response = client.post("/api/v1/identity/verify", json={"token": "dev-token"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_expert_mode_draft_numbers_unique() -> None:
    """同日两次专家创建 → 草稿工单号不同（终审 C2）。"""
    draft = {
        "module": "AKO_quote_agent", "action": "审计", "scope": "只动报价校验",
        "rules": ["不修改生产环境"], "prohibitions": ["禁止直接修改生产数据库"],
        "deliverable": "输出审计报告", "deadline": "90分钟",
    }
    a = client.post("/api/v1/intake/sessions", json={"draft_wo": draft}).json()
    b = client.post("/api/v1/intake/sessions", json={"draft_wo": draft}).json()
    wa = client.get(f"/api/v1/intake/sessions/{a['session_id']}").json()["draft_work_order"]["wo_number"]
    wb = client.get(f"/api/v1/intake/sessions/{b['session_id']}").json()["draft_work_order"]["wo_number"]
    assert wa != wb


def test_rest_auth_dev_mode_passthrough() -> None:
    """identity 未配置（开发态）→ 无 Authorization 头仍放行。"""
    assert client.get("/metrics").status_code == 200


def test_rest_auth_blocks_when_identity_configured(monkeypatch) -> None:
    """identity 已配置且不可达 → 401。"""
    monkeypatch.setattr(app_module.config, "gateways", type(app_module.config.gateways)(identity_base_url="http://127.0.0.1:9", registry_base_url="", hub_base_url=""))
    response = client.get("/metrics")
    assert response.status_code == 401


def test_create_session_raw_text_runs_pipeline() -> None:
    """raw_text 走自然语言链路（spec 3.5.2，终审 I2）。"""
    response = client.post("/api/v1/intake/sessions", json={"raw_text": "修复报价模块的bug，只动校验逻辑，不动数据库"})
    assert response.status_code == 200
    assert response.json()["status"] in ("DELIVERED", "CLARIFYING", "MANUAL_REVIEW", "FORM_BUILDING")


def test_ws_auth_timeout_closes(monkeypatch) -> None:
    """连接后未发 auth → 超时关闭（spec 3.2.1，终审 I5）。"""
    monkeypatch.setattr(app_module.config, "ws", type(app_module.config.ws)(heartbeat_seconds=30, stream_ack_bytes=16384, auth_timeout_seconds=0.05))
    with client.websocket_connect("/ws/intake") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert data["payload"]["code"] == "AUTH_REQUIRED"

