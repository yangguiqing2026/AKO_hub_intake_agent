"""WS v2 消息模型契约测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ako_intake.models import BootstrapConfig, InboundMessage, OutboundMessage, TermBrief


def test_parse_auth_message() -> None:
    msg = InboundMessage.model_validate({"v": 2, "type": "auth", "payload": {"token": "t-1"}})
    assert msg.type == "auth"
    assert msg.payload.token == "t-1"


def test_parse_intake_input_message() -> None:
    raw = {
        "v": 2,
        "type": "intake_input",
        "session_id": "sess-1",
        "req_id": "req-a1",
        "payload": {"text": "修复报价模块的bug，只动校验逻辑，不动数据库"},
    }
    msg = InboundMessage.model_validate(raw)
    assert msg.type == "intake_input"
    assert msg.session_id == "sess-1"
    assert msg.req_id == "req-a1"
    assert len(msg.payload.text) >= 10


def test_parse_p0_response_message() -> None:
    raw = {
        "v": 2,
        "type": "p0_response",
        "session_id": "sess-1",
        "payload": {"round": 1, "answers": [{"qid": "q-1-action", "value": "审计"}], "conservative": False},
    }
    msg = InboundMessage.model_validate(raw)
    assert msg.payload.answers[0].value == "审计"


def test_reject_unknown_type() -> None:
    with pytest.raises(ValidationError):
        InboundMessage.model_validate({"v": 2, "type": "not_a_type", "payload": {}})


def test_intake_input_too_short_rejected() -> None:
    with pytest.raises(ValidationError):
        InboundMessage.model_validate({"v": 2, "type": "intake_input", "payload": {"text": "hi"}})


def test_outbound_message_defaults() -> None:
    msg = OutboundMessage(type="status", session_id="s", seq=1, ts="t", payload={"status": "IDLE"})
    assert msg.v == 2
    assert msg.model_dump()["v"] == 2


def test_bootstrap_config_schema() -> None:
    cfg = BootstrapConfig(agent_id="AKO_hub_intake_agent", terms=[TermBrief(term="报价", module="AKO_quote_agent", actions=["审计"])])
    assert cfg.terms[0].actions == ["审计"]
