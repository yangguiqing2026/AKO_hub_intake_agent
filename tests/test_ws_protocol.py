"""WS v2 协议处理器测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ako_intake.adapters.ws_protocol import WsSessionHandler
from ako_intake.config import AppConfig, DbSettings, GatewaySettings, TermEntry
from ako_intake.core.graph import compile_graph
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
from ako_intake.llm.budget import BudgetTracker
from ako_intake.services.observability import Metrics


def _cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        gateways=GatewaySettings(hub_base_url="", registry_base_url="", identity_base_url=""),
        db=DbSettings(
            session_db=str(tmp_path / "s.db"),
            queue_db=str(tmp_path / "q.db"),
            archive_dir=str(tmp_path / "a"),
        ),
        terms=[TermEntry(term="报价", module="AKO_quote_agent", actions=["审计", "修复", "查看"])],
    ).resolve_paths()


def _handler(tmp_path: Path, budget: Optional[BudgetTracker] = None) -> WsSessionHandler:
    config = _cfg(tmp_path)
    return WsSessionHandler(
        config,
        SessionStore(config.db.session_db),
        QueueStore(config.db.queue_db),
        compile_graph(config),
        Metrics(),
        budget=budget,
    )


def _send(handler: WsSessionHandler, msg: dict) -> list[dict]:
    return [m.model_dump(exclude_none=True) for m in handler.handle_text(json.dumps(msg, ensure_ascii=False))]


AUTH = {"v": 2, "type": "auth", "payload": {"token": "dev-token"}}
INPUT = {
    "v": 2,
    "type": "intake_input",
    "payload": {"text": "修复报价模块的bug，只动校验逻辑，不动数据库"},
}


def test_auth_then_hello(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    out = _send(handler, AUTH)
    assert out[0]["type"] == "hello"
    assert out[0]["payload"]["protocol_version"] == 2
    assert out[0]["payload"]["bootstrap"]["agent_id"] == "AKO_hub_intake_agent"


def test_business_message_before_auth_rejected(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    out = _send(handler, INPUT)
    assert out[0]["type"] == "error"
    assert out[0]["payload"]["code"] == "AUTH_REQUIRED"


def test_unknown_message_type(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    out = _send(handler, {"v": 2, "type": "no_such_type", "payload": {}})
    assert out[0]["payload"]["code"] == "INVALID_MESSAGE_TYPE"


def test_intake_input_flow_to_delivered(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    types = [m["type"] for m in out]
    assert "status" in types
    assert "wo_preview" in types
    assert "review_result" in types
    final_status = [m for m in out if m["type"] == "status"][-1]
    assert final_status["payload"]["status"] == "DELIVERED"


def test_clarifying_then_answer_flow(tmp_path: Path) -> None:
    """2026-09-04 一问一答：action 一问→scope 一问→投递。"""
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, {"v": 2, "type": "intake_input", "payload": {"text": "帮我看看报价模块的数据"}})
    inter = [m for m in out if m["type"] == "p0_interrogation"]
    assert inter, "应触发 P0 反问"
    session_id = inter[0]["session_id"]
    q1 = inter[0]["payload"]["questions"][0]
    assert q1["field"] == "action"
    out2 = _send(handler, {"v": 2, "type": "p0_response", "session_id": session_id, "payload": {"round": 1, "answers": [{"qid": q1["qid"], "value": "审计"}]}})
    inter2 = [m for m in out2 if m["type"] == "p0_interrogation"]
    assert inter2, "应追问 scope"
    q2 = inter2[0]["payload"]["questions"][0]
    assert q2["field"] == "scope"
    out3 = _send(handler, {"v": 2, "type": "p0_response", "session_id": session_id, "payload": {"round": 2, "answers": [{"qid": q2["qid"], "value": "全局审计，不动数据"}]}})
    assert [m for m in out3 if m["type"] == "status"][-1]["payload"]["status"] == "DELIVERED"


def test_conservative_response_to_manual_review(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, {"v": 2, "type": "intake_input", "payload": {"text": "帮我看看报价模块的数据"}})
    inter = [m for m in out if m["type"] == "p0_interrogation"][0]
    out2 = _send(handler, {"v": 2, "type": "p0_response", "session_id": inter["session_id"], "payload": {"round": 1, "answers": [], "conservative": True}})
    assert [m for m in out2 if m["type"] == "manual_review"], "保守策略应入人工审核"


def test_wo_confirm_with_hub_down_queues_locally(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    out2 = _send(handler, {"v": 2, "type": "wo_confirm", "session_id": session_id, "payload": {}})
    assert [m for m in out2 if m["type"] == "queued_local"], "Hub 不可达应入本地队列"
    assert handler.queue_store.stats().get("pending", 0) >= 1


def test_session_resume_returns_snapshot(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    out2 = _send(handler, {"v": 2, "type": "session_resume", "payload": {"session_id": session_id}})
    snap = [m for m in out2 if m["type"] == "session_snapshot"][0]
    assert snap["payload"]["state"]["session_id"] == session_id
    assert snap["seq"] >= 1


def test_wo_edit_updates_preview(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    out2 = _send(handler, {"v": 2, "type": "wo_edit", "session_id": session_id, "payload": {"draft_wo": {"scope": "只动A模块"}}})
    preview = [m for m in out2 if m["type"] == "wo_preview"][0]
    assert preview["payload"]["draft_wo"]["scope"] == "只动A模块"


def test_seq_monotonic_per_session(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    out = _send(handler, AUTH)
    hello_seq = out[0]["seq"]
    out2 = _send(handler, INPUT)
    seqs = [m["seq"] for m in out2]
    assert hello_seq == 1
    # 按会话单调递增、从 1 起（设计 3.3）；hello 属 "" 会话计数器，新会话独立从 1 开始
    assert seqs == list(range(1, 1 + len(seqs)))


def test_wo_edit_after_discard_returns_error(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    _send(handler, {"v": 2, "type": "wo_discard", "session_id": session_id, "payload": {}})
    out2 = _send(handler, {"v": 2, "type": "wo_edit", "session_id": session_id, "payload": {"draft_wo": {"scope": "只动A模块"}}})
    assert out2[0]["type"] == "error"
    assert out2[0]["payload"]["code"] == "INVALID_PAYLOAD"


def test_wo_edit_bad_field_type_returns_invalid_payload(tmp_path: Path) -> None:
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    out2 = _send(handler, {"v": 2, "type": "wo_edit", "session_id": session_id, "payload": {"draft_wo": {"rules": 123}}})
    assert out2[0]["type"] == "error"
    assert out2[0]["payload"]["code"] == "INVALID_PAYLOAD"


def test_session_resume_seq_consistent(tmp_path: Path) -> None:
    """快照 payload.seq 与信封 seq 一致，且下一条消息信封 seq 连续（终审 C1）。"""
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    out2 = _send(handler, {"v": 2, "type": "session_resume", "payload": {"session_id": session_id}})
    snap = [m for m in out2 if m["type"] == "session_snapshot"][0]
    assert snap["payload"]["seq"] == snap["seq"]
    out3 = _send(handler, {"v": 2, "type": "ping", "session_id": session_id, "payload": {}})
    assert out3[0]["seq"] == snap["seq"] + 1


# ---- 预算软熔断生命周期（跃迁检测发射，缺口 1）----

PING = {"v": 2, "type": "ping", "payload": {}}


def _soft_break_of(out: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    hits = [m for m in out if m["type"] == "soft_break"]
    return hits[0]["payload"] if hits else None


def test_soft_break_activated_edge_emitted_once(tmp_path: Path) -> None:
    """用量跨过阈值 → 下一条入站消息响应携带 soft_break{active:true}；同态再触发不重复发射。"""
    tracker = BudgetTracker(monthly_quota_tokens=100_000)
    handler = _handler(tmp_path, budget=tracker)
    _send(handler, AUTH)
    tracker.record("x", 5_000)  # 恰 5.0%，跨阈
    out = _send(handler, PING)
    payload = _soft_break_of(out)
    assert payload is not None
    assert payload["active"] is True
    assert payload["usage_percent"] == 5.0
    assert payload["monthly_quota_tokens"] == 100_000
    assert [m for m in out if m["type"] == "pong"], "ping 应答不受软熔断消息影响"
    out2 = _send(handler, PING)
    assert _soft_break_of(out2) is None, "无沿变化不重复发射"


def test_soft_break_cleared_edge_on_quota_raise(tmp_path: Path) -> None:
    """进程内配额上调（唯一解除途径）→ 下条消息响应携带 soft_break{active:false}。"""
    tracker = BudgetTracker(monthly_quota_tokens=100_000)
    handler = _handler(tmp_path, budget=tracker)
    _send(handler, AUTH)
    tracker.record("x", 5_000)
    out = _send(handler, PING)
    assert _soft_break_of(out)["active"] is True
    tracker.set_quota(1_000_000)
    out2 = _send(handler, PING)
    payload = _soft_break_of(out2)
    assert payload is not None
    assert payload["active"] is False


def test_soft_break_no_edge_no_message(tmp_path: Path) -> None:
    """用量未跨阈 → 全程无 soft_break 消息。"""
    tracker = BudgetTracker(monthly_quota_tokens=100_000)
    handler = _handler(tmp_path, budget=tracker)
    _send(handler, AUTH)
    tracker.record("x", 1_000)  # 1.0%，未跨阈
    out = _send(handler, PING)
    assert _soft_break_of(out) is None
    out2 = _send(handler, PING)
    assert _soft_break_of(out2) is None


def test_wo_edit_resets_human_confirmed(tmp_path: Path) -> None:
    """编辑草稿后旧的人工确认失效（M07 门禁防绕过，缺口 2）。"""
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    state = handler.session_store.load(session_id)
    assert state is not None
    state["human_confirmed"] = True
    handler.session_store.save(session_id, "REVIEWING", state)
    out2 = _send(handler, {"v": 2, "type": "wo_edit", "session_id": session_id, "payload": {"draft_wo": {"scope": "只动A模块"}}})
    assert [m for m in out2 if m["type"] == "wo_preview"], "编辑应回 wo_preview"
    updated = handler.session_store.load(session_id)
    assert updated is not None
    assert updated.get("human_confirmed") is False
