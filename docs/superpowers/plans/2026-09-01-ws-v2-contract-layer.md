# WS v2 契约层实现计划（Phase A）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AKO_hub_intake_agent 后端（FastAPI :5026）的前后契约升级为 WS v2 信封协议 + 新增 REST 端点，修复 P1~P8 中的后端侧问题，并通过 schemas/ 契约测试锁定双端一致。

**Architecture:** 在现有 `app.py`（FastAPI + LangGraph）之上新增 `ako_intake/adapters/ws_protocol.py` 协议处理器（消息白名单 + Pydantic 判别联合校验 + 按会话 seq 序号 + 状态→事件翻译 + 快照），WS 端点改为接入该处理器；新增 bootstrap/会话/队列/身份 REST 端点；`schemas/` 契约文件由 Pydantic 模型导出并加测试防漂移。

**Tech Stack:** Python 3.10+ / FastAPI / Pydantic v2 / LangGraph（既有）/ pytest。

**Spec:** `docs/AKO_hub_intake_frontend_contract_v1.0.0.md`（本计划实现其第三、五、六、七章的后端部分与第八章 Phase A 改动清单；前端部分由后续 Plan 2 实现）。

## Global Constraints

- 后端端口统一 **5026**（修正 `config/intake_config.yaml` 中误改的 5027，见设计附录 B / R1）。
- 不修改 `web/` 前端任何文件（Plan 2 负责）；前端可依据本计划的 schemas/ 契约并行 mock 开发。
- 遵循既有代码风格：中文模块 docstring、全量类型注解、模块职责单一（参考 `ako_intake/core/`、`gateways/` 现有写法）。
- 测试：pytest，`testpaths = tests`，`--basetemp=.pytest_tmp`；每个新函数/端点必须有测试。
- 消息信封 `v` 恒为 2；出站消息 `seq` 按会话单调递增；PII 出站前脱敏（`ako_intake/utils/pii.py`）。
- 身份门禁：`gateways.identity_base_url` 未配置时开发态模拟放行（仅非生产，设计 R3）；registry 未配置时不拦截（设计 5.3 门禁第二重仅在配置后生效）。
- 现有 18 个测试文件必须全部回归通过（含更新的 `test_app.py`）。

---

### Task 1: WS v2 消息模型（Pydantic 判别联合）

**Files:**
- Modify: `ako_intake/models.py`（追加 WS v2 消息模型）
- Test: `tests/test_ws_models.py`（新建）

**Interfaces:**
- Consumes: 无（纯模型层）。
- Produces:
  - `InboundMessage = Annotated[Union[AuthMessage, IntakeInputMessage, P0ResponseMessage, WoEditMessage, WoConfirmMessage, WoDiscardMessage, SessionResumeMessage, SessionAbandonMessage, StreamAckMessage, PingMessage], Field(discriminator="type")]`
  - `AuthMessage.payload: AuthPayload{token}`
  - `IntakeInputMessage.payload: IntakeInputPayload{text: 10..2000}`
  - `P0ResponseMessage.payload: P0ResponsePayload{round: ge=1, answers: list[AnswerItem{qid,value}], conservative: bool=False}`
  - `WoEditMessage.payload: WoEditPayload{draft_wo: dict}`
  - `SessionResumeMessage.payload: SessionResumePayload{session_id}`
  - `StreamAckMessage.payload: StreamAckPayload{stream_id, bytes: ge=0}`
  - `OutboundMessage(BaseModel): v=2, type, req_id="", session_id="", seq=0, ts="", payload: dict`
  - `TermBrief(BaseModel): term, module, actions: list[str]`
  - `BootstrapConfig(BaseModel): agent_id, version, terms: list[TermBrief], intake: dict, budget: dict, llm: dict, knowledge_enabled, identity_required, ws: dict, observability: dict`
  - `ErrorPayload(BaseModel): code, message`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_ws_models.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_ws_models.py -v`
Expected: FAIL，`ImportError: cannot import name 'InboundMessage' from 'ako_intake.models'`

- [ ] **Step 3: 实现模型**

在 `ako_intake/models.py` 末尾追加：

```python
class WSEnvelopeMixin(BaseModel):
    """WS v2 信封公共字段（除 type/payload 外）。"""

    v: Literal[2] = 2
    req_id: str = ""
    session_id: str = ""


class AuthPayload(BaseModel):
    token: str = Field(min_length=1)


class IntakeInputPayload(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class AnswerItem(BaseModel):
    qid: str
    value: str


class P0ResponsePayload(BaseModel):
    round: int = Field(ge=1)
    answers: List[AnswerItem] = Field(default_factory=list)
    conservative: bool = False


class WoEditPayload(BaseModel):
    draft_wo: Dict[str, Any] = Field(default_factory=dict)


class SessionResumePayload(BaseModel):
    session_id: str = Field(min_length=1)


class StreamAckPayload(BaseModel):
    stream_id: str
    bytes: int = Field(ge=0)


class EmptyPayload(BaseModel):
    pass


class AuthMessage(WSEnvelopeMixin):
    type: Literal["auth"] = "auth"
    payload: AuthPayload


class IntakeInputMessage(WSEnvelopeMixin):
    type: Literal["intake_input"] = "intake_input"
    payload: IntakeInputPayload


class P0ResponseMessage(WSEnvelopeMixin):
    type: Literal["p0_response"] = "p0_response"
    payload: P0ResponsePayload


class WoEditMessage(WSEnvelopeMixin):
    type: Literal["wo_edit"] = "wo_edit"
    payload: WoEditPayload


class WoConfirmMessage(WSEnvelopeMixin):
    type: Literal["wo_confirm"] = "wo_confirm"
    payload: EmptyPayload


class WoDiscardMessage(WSEnvelopeMixin):
    type: Literal["wo_discard"] = "wo_discard"
    payload: EmptyPayload


class SessionResumeMessage(WSEnvelopeMixin):
    type: Literal["session_resume"] = "session_resume"
    payload: SessionResumePayload


class SessionAbandonMessage(WSEnvelopeMixin):
    type: Literal["session_abandon"] = "session_abandon"
    payload: EmptyPayload


class StreamAckMessage(WSEnvelopeMixin):
    type: Literal["stream_ack"] = "stream_ack"
    payload: StreamAckPayload


class PingMessage(WSEnvelopeMixin):
    type: Literal["ping"] = "ping"
    payload: EmptyPayload


class InboundMessage(RootModel[Annotated[Union[
    AuthMessage,
    IntakeInputMessage,
    P0ResponseMessage,
    WoEditMessage,
    WoConfirmMessage,
    WoDiscardMessage,
    SessionResumeMessage,
    SessionAbandonMessage,
    StreamAckMessage,
    PingMessage,
], Field(discriminator="type")]]):
    """入站消息判别联合。

    Pydantic v2 中裸 ``Annotated[Union[...], Field(discriminator=...)]`` 别名
    无模型方法（GH #10409），以 RootModel 包装获得 ``model_validate`` /
    ``model_json_schema``；``__getattr__`` 委托使 ``msg.type`` /
    ``msg.payload`` 等直接可访问。
    """

    def __getattr__(self, name: str) -> Any:
        """委托到 .root，保持消息字段直接访问语义。"""
        return getattr(self.root, name)


class ErrorPayload(BaseModel):
    code: str
    message: str


class OutboundMessage(BaseModel):
    """WS v2 出站信封。seq/ts 由协议处理器填充。"""

    v: int = 2
    type: str
    req_id: str = ""
    session_id: str = ""
    seq: int = 0
    ts: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class TermBrief(BaseModel):
    term: str
    module: str
    actions: List[str] = Field(default_factory=list)


class BootstrapConfig(BaseModel):
    agent_id: str = ""
    version: str = "0.1.0"
    terms: List[TermBrief] = Field(default_factory=list)
    intake: Dict[str, Any] = Field(default_factory=dict)
    budget: Dict[str, Any] = Field(default_factory=dict)
    llm: Dict[str, Any] = Field(default_factory=dict)
    knowledge_enabled: bool = False
    identity_required: bool = False
    ws: Dict[str, Any] = Field(default_factory=dict)
    observability: Dict[str, Any] = Field(default_factory=dict)
```

注意：`models.py` 顶部已 `from typing import Any, Dict, List, Literal, Optional` 与 `from pydantic import BaseModel, Field`；需追加 `from typing import Annotated, Union` 与 `from pydantic import RootModel`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_ws_models.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add ako_intake/models.py tests/test_ws_models.py
git commit -m "feat(intake): WS v2 消息模型（Pydantic 判别联合）"
```

---

### Task 2: WS v2 协议处理器

**Files:**
- Create: `ako_intake/adapters/ws_protocol.py`
- Test: `tests/test_ws_protocol.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `InboundMessage`/`OutboundMessage`/`BootstrapConfig`；既有 `ako_intake/config.py`（AppConfig）、`db/session_store.py`（SessionStore）、`db/queue_store.py`（QueueStore）、`core/graph.py`（compile_graph）、`gateways/hub_client.py`（HubClient）、`gateways/registry_client.py`（verify_target）、`gateways/identity_client.py`（verify_human）、`services/form_builder.py`（validate_work_order）、`services/reviewer.py`（review_work_order）、`services/observability.py`（Metrics）、`core/pipeline.py`（deliver_with_local_queue）、`utils/pii.py`（mask_pii）。
- Produces:
  - `INBOUND_TYPES: set[str]`（10 类入站白名单）
  - `class ProtocolError(Exception)`（`code`/`message`）
  - `def mask_pii_dict(obj: Any) -> Any`（递归脱敏）
  - `def bootstrap_payload(config: AppConfig, budget: object | None = None) -> dict[str, Any]`
  - `class WsSessionHandler`：
    - `__init__(self, config, session_store, queue_store, graph, metrics, budget=None)`
    - `handle_text(self, raw: str) -> list[OutboundMessage]`（主入口，永抛异常，错误转 `error` 消息）
    - `next_seq(self, session_id: str) -> int`
    - `_msg(self, type_, session_id, payload=None, req_id="") -> OutboundMessage`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_ws_protocol.py`：

```python
"""WS v2 协议处理器测试。"""

from __future__ import annotations

import json
from pathlib import Path

from ako_intake.adapters.ws_protocol import WsSessionHandler
from ako_intake.config import AppConfig, DbSettings, GatewaySettings, TermEntry
from ako_intake.core.graph import compile_graph
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
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


def _handler(tmp_path: Path) -> WsSessionHandler:
    config = _cfg(tmp_path)
    return WsSessionHandler(
        config,
        SessionStore(config.db.session_db),
        QueueStore(config.db.queue_db),
        compile_graph(config),
        Metrics(),
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
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, {"v": 2, "type": "intake_input", "payload": {"text": "帮我看看报价模块的数据"}})
    inter = [m for m in out if m["type"] == "p0_interrogation"]
    assert inter, "应触发 P0 反问"
    session_id = inter[0]["session_id"]
    questions = inter[0]["payload"]["questions"]
    answers = [{"qid": q["qid"], "value": "审计" if q["field"] == "action" else "全局审计，不动数据"} for q in questions]
    out2 = _send(handler, {"v": 2, "type": "p0_response", "session_id": session_id, "payload": {"round": 1, "answers": answers}})
    assert [m for m in out2 if m["type"] == "status"][-1]["payload"]["status"] == "DELIVERED"


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
    """wo_discard 清空草稿后 wo_edit 不崩溃（修复轮 1 覆盖）。"""
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    _send(handler, {"v": 2, "type": "wo_discard", "session_id": session_id, "payload": {}})
    out2 = _send(handler, {"v": 2, "type": "wo_edit", "session_id": session_id, "payload": {"draft_wo": {"scope": "只动A"}}})
    assert out2[0]["type"] == "error"
    assert out2[0]["payload"]["code"] == "INVALID_PAYLOAD"


def test_wo_edit_bad_field_type_returns_invalid_payload(tmp_path: Path) -> None:
    """wo_edit 携带错误类型字段（如 rules=123）→ error(INVALID_PAYLOAD) 而非断连。"""
    handler = _handler(tmp_path)
    _send(handler, AUTH)
    out = _send(handler, INPUT)
    session_id = [m for m in out if m["type"] == "wo_preview"][0]["session_id"]
    out2 = _send(handler, {"v": 2, "type": "wo_edit", "session_id": session_id, "payload": {"draft_wo": {"rules": 123}}})
    assert out2[0]["type"] == "error"
    assert out2[0]["payload"]["code"] == "INVALID_PAYLOAD"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_ws_protocol.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'ako_intake.adapters.ws_protocol'`

- [ ] **Step 3: 实现处理器**

创建 `ako_intake/adapters/ws_protocol.py`：

```python
"""WS v2 协议处理器：白名单 + 判别联合校验 + seq 序号 + 状态→事件翻译 + 快照。

设计依据：docs/AKO_hub_intake_frontend_contract_v1.0.0.md 第三章。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ako_intake.config import AppConfig
from ako_intake.core.graph import compile_graph
from ako_intake.core.pipeline import deliver_with_local_queue
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
from ako_intake.gateways.hub_client import HubClient
from ako_intake.gateways.identity_client import verify_human
from ako_intake.gateways.registry_client import verify_target
from ako_intake.models import (
    Ako1WorkOrder,
    Answer,
    BootstrapConfig,
    InboundMessage,
    OutboundMessage,
    TermBrief,
)
from ako_intake.services.form_builder import validate_work_order
from ako_intake.services.observability import Metrics
from ako_intake.services.reviewer import review_work_order
from ako_intake.utils.pii import mask_pii

INBOUND_TYPES = {
    "auth",
    "intake_input",
    "p0_response",
    "wo_edit",
    "wo_confirm",
    "wo_discard",
    "session_resume",
    "session_abandon",
    "stream_ack",
    "ping",
}


class ProtocolError(Exception):
    """协议错误（转为 error 出站消息，不中断连接）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def mask_pii_dict(obj: Any) -> Any:
    """递归脱敏（出站前调用，PII_RESTRICTED）。"""
    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, list):
        return [mask_pii_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {key: mask_pii_dict(value) for key, value in obj.items()}
    return obj


def bootstrap_payload(config: AppConfig, budget: Any = None) -> Dict[str, Any]:
    """构造 /bootstrap 与 hello.bootstrap 负载。"""
    usage_percent = float(budget.usage_percent()) if budget is not None else 0.0
    soft_break_active = bool(budget.should_soft_break(config.budget.soft_limit_percent)) if budget is not None else False
    return BootstrapConfig(
        agent_id=config.agent_id,
        version="0.1.0",
        terms=[TermBrief(term=t.term, module=t.module, actions=list(t.actions)) for t in config.terms],
        intake={
            "max_p0_rounds": config.intake.max_p0_rounds,
            "question_timeout_seconds": config.intake.question_timeout_seconds,
            "max_questions_per_round": config.intake.max_questions_per_round,
            "review_score_threshold": config.intake.review_score_threshold,
        },
        budget={
            "soft_limit_percent": config.budget.soft_limit_percent,
            "monthly_quota_tokens": config.budget.monthly_quota_tokens,
            "usage_percent": usage_percent,
            "soft_break_active": soft_break_active,
        },
        llm={
            "use_llm": config.llm_router.use_llm,
            "simple": config.llm_router.simple,
            "complex": config.llm_router.complex,
        },
        knowledge_enabled=config.knowledge_enabled,
        identity_required=bool(config.gateways.identity_base_url),
        ws={
            "heartbeat_seconds": config.ws.heartbeat_seconds,
            "stream_ack_bytes": config.ws.stream_ack_bytes,
            "auth_timeout_seconds": config.ws.auth_timeout_seconds,
        },
        observability={"sentry_dsn": ""},
    ).model_dump()


class WsSessionHandler:
    """单 WS 连接的协议处理器（无状态偏服务端，会话状态存 SessionStore）。"""

    def __init__(
        self,
        config: AppConfig,
        session_store: SessionStore,
        queue_store: QueueStore,
        graph: Any,
        metrics: Metrics,
        budget: Any = None,
    ) -> None:
        self.config = config
        self.session_store = session_store
        self.queue_store = queue_store
        self.graph = graph
        self.metrics = metrics
        self.budget = budget
        self.authenticated = False
        self.identity: str = ""
        self._seqs: Dict[str, int] = {}

    # ---- 序号与消息构造 ----

    def next_seq(self, session_id: str) -> int:
        seq = self._seqs.get(session_id, 0) + 1
        self._seqs[session_id] = seq
        return seq

    def _msg(self, type_: str, session_id: str, payload: Optional[Dict[str, Any]] = None, req_id: str = "") -> OutboundMessage:
        return OutboundMessage(
            type=type_,
            req_id=req_id,
            session_id=session_id,
            seq=self.next_seq(session_id),
            ts=datetime.now().isoformat(),
            payload=payload or {},
        )

    def _err(self, code: str, message: str, req_id: str = "") -> OutboundMessage:
        return self._msg("error", "", {"code": code, "message": message}, req_id=req_id)

    # ---- 主入口 ----

    def handle_text(self, raw: str) -> List[OutboundMessage]:
        """处理一条入站文本；所有异常转为 error 出站消息。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return [self._err("INVALID_PAYLOAD", f"JSON 解析失败: {exc}")]
        if not isinstance(data, dict) or data.get("v") != 2:
            return [self._err("PROTOCOL_VERSION_MISMATCH", "协议版本必须为 2")]
        req_id = str(data.get("req_id", ""))
        msg_type = data.get("type")
        if msg_type not in INBOUND_TYPES:
            return [self._err("INVALID_MESSAGE_TYPE", f"未知消息类型: {msg_type}", req_id)]
        if not self.authenticated and msg_type != "auth":
            return [self._err("AUTH_REQUIRED", "请先发送 auth", req_id)]
        try:
            msg = InboundMessage.model_validate(data)
        except ValidationError as exc:
            return [self._err("INVALID_PAYLOAD", f"负载校验失败: {exc}", req_id)]
        try:
            handler = getattr(self, f"_on_{msg_type}")
            return handler(msg)
        except ProtocolError as exc:
            return [self._err(exc.code, exc.message, req_id)]
        except ValidationError as exc:
            return [self._err("INVALID_PAYLOAD", f"负载校验失败: {exc}", req_id)]
        except Exception as exc:
            return [self._err("INTERNAL", f"处理失败: {exc}", req_id)]

    # ---- 入站处理器 ----

    def _on_auth(self, msg: InboundMessage) -> List[OutboundMessage]:
        result = verify_human(msg.payload.token, self.config.gateways.identity_base_url)
        if not result.get("ok"):
            raise ProtocolError("AUTH_REQUIRED", f"身份校验失败: {result.get('error', '')}")
        self.authenticated = True
        self.identity = str(result.get("human_id", ""))
        return [
            self._msg(
                "hello",
                "",
                {
                    "protocol_version": 2,
                    "server_time": datetime.now().isoformat(),
                    "session_id": "",
                    "bootstrap": bootstrap_payload(self.config, self.budget),
                },
                req_id=msg.req_id,
            )
        ]

    def _on_intake_input(self, msg: InboundMessage) -> List[OutboundMessage]:
        session_id = msg.session_id or f"sess-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        state = {
            "session_id": session_id,
            "status": "PARSING",
            "raw_input": msg.payload.text,
            "clarification_log": [],
            "pending_answers": [],
            "p0_rounds": 0,
            "queue": "main",
        }
        self.metrics.increment("sessions_total")
        out = [self._msg("status", session_id, {"status": "PARSING"}, req_id=msg.req_id)]
        result = self.graph.invoke(state)
        self.session_store.save(session_id, str(result.get("status", "UNKNOWN")), result)
        out.extend(self._events_from_state(result, msg.req_id))
        return out

    def _on_p0_response(self, msg: InboundMessage) -> List[OutboundMessage]:
        session_id = msg.session_id
        state = self.session_store.load(session_id)
        if state is None:
            raise ProtocolError("SESSION_NOT_FOUND", "会话不存在")
        if msg.payload.conservative:
            # 用户选择"按最保守策略处理"（US-002）→ 直接触发 7.1 降级（人工审核）
            state["pending_answers"] = []
            state["p0_rounds"] = self.config.intake.max_p0_rounds
        else:
            # graph.interrogate_node → apply_answers 需要 Answer 实例（非 dict）
            state["pending_answers"] = [Answer.model_validate(a.model_dump()) for a in msg.payload.answers]
        result = self.graph.invoke(state)
        self.session_store.save(session_id, str(result.get("status", "UNKNOWN")), result)
        return self._events_from_state(result, msg.req_id)

    def _on_wo_edit(self, msg: InboundMessage) -> List[OutboundMessage]:
        session_id = msg.session_id
        state = self.session_store.load(session_id)
        if state is None:
            raise ProtocolError("SESSION_NOT_FOUND", "会话不存在")
        merged = {**(state.get("draft_work_order") or {}), **msg.payload.draft_wo}
        wo = Ako1WorkOrder.model_validate(merged)
        problems = validate_work_order(wo)
        if problems:
            raise ProtocolError("SCHEMA_ERROR", "; ".join(problems))
        record = review_work_order(wo, self.config.intake.review_score_threshold)
        state["draft_work_order"] = wo.model_dump()
        state["review_record"] = record.model_dump()
        state["status"] = "REVIEWING"
        self.session_store.save(session_id, "REVIEWING", state)
        return [
            self._msg(
                "wo_preview",
                session_id,
                {
                    "draft_wo": mask_pii_dict(wo.model_dump()),
                    "confidence_score": wo.confidence_score,
                    "review_record": record.model_dump(),
                    "actions": ["confirm", "edit", "discard"],
                },
                req_id=msg.req_id,
            ),
            self._msg("review_result", session_id, {"review_record": record.model_dump()}, req_id=msg.req_id),
        ]

    def _on_wo_confirm(self, msg: InboundMessage) -> List[OutboundMessage]:
        session_id = msg.session_id
        state = self.session_store.load(session_id)
        if state is None:
            raise ProtocolError("SESSION_NOT_FOUND", "会话不存在")
        wo_data = state.get("draft_work_order")
        if not wo_data:
            raise ProtocolError("INVALID_PAYLOAD", "无草稿工单可投递")
        # 第二重门禁：等级校验（仅 registry 已配置时拦截，设计 5.3）
        if self.config.gateways.registry_base_url:
            verify = verify_target(wo_data.get("module", ""), "AKO_hub_intake_agent", self.config.gateways.registry_base_url)
            if not verify.deployable:
                state["status"] = "MANUAL_REVIEW"
                state["queue"] = "manual_review"
                state["error"] = "REGISTRY_BLOCKED"
                self.session_store.save(session_id, "MANUAL_REVIEW", state)
                return [self._msg("manual_review", session_id, {"draft_wo": mask_pii_dict(wo_data), "reason": "REGISTRY_BLOCKED"}, req_id=msg.req_id)]
        hub = HubClient(self.config.gateways.hub_base_url)
        result = deliver_with_local_queue(state, self.config, hub, self.queue_store)
        self.session_store.save(session_id, str(result.get("status", "UNKNOWN")), result)
        return self._events_from_state(result, msg.req_id)

    def _on_wo_discard(self, msg: InboundMessage) -> List[OutboundMessage]:
        session_id = msg.session_id
        state = self.session_store.load(session_id)
        if state is None:
            raise ProtocolError("SESSION_NOT_FOUND", "会话不存在")
        state["draft_work_order"] = None
        state["status"] = "IDLE"
        self.session_store.save(session_id, "IDLE", state)
        return [self._msg("status", session_id, {"status": "IDLE"}, req_id=msg.req_id)]

    def _on_session_resume(self, msg: InboundMessage) -> List[OutboundMessage]:
        session_id = msg.payload.session_id
        state = self.session_store.load(session_id)
        if state is None:
            raise ProtocolError("SESSION_NOT_FOUND", "会话不存在")
        return [
            self._msg(
                "session_snapshot",
                session_id,
                {"state": mask_pii_dict(state), "seq": self.next_seq(session_id)},
                req_id=msg.req_id,
            )
        ]

    def _on_session_abandon(self, msg: InboundMessage) -> List[OutboundMessage]:
        session_id = msg.session_id
        state = self.session_store.load(session_id)
        if state is None:
            raise ProtocolError("SESSION_NOT_FOUND", "会话不存在")
        state["status"] = "ABANDONED"
        self.session_store.save(session_id, "ABANDONED", state)
        return [self._msg("status", session_id, {"status": "ABANDONED"}, req_id=msg.req_id)]

    def _on_stream_ack(self, msg: InboundMessage) -> List[OutboundMessage]:
        # 流控确认，Phase A 无流式输出，仅接受
        return []

    def _on_ping(self, msg: InboundMessage) -> List[OutboundMessage]:
        return [self._msg("pong", "", {}, req_id=msg.req_id)]

    # ---- 状态→事件翻译 ----

    def _events_from_state(self, state: Dict[str, Any], req_id: str = "") -> List[OutboundMessage]:
        """LangGraph 终态 → 出站事件序列（设计 3.2.2/3.3）。"""
        session_id = str(state.get("session_id", ""))
        status = str(state.get("status", "UNKNOWN"))
        out: List[OutboundMessage] = [self._msg("status", session_id, {"status": status}, req_id=req_id)]
        if status == "CLARIFYING":
            out.append(
                self._msg(
                    "p0_interrogation",
                    session_id,
                    {
                        "round": int(state.get("p0_rounds", 0)),
                        "questions": state.get("pending_questions", []),
                        "timeout_seconds": self.config.intake.question_timeout_seconds,
                        "expires_at": (
                            datetime.now() + timedelta(seconds=self.config.intake.question_timeout_seconds)
                        ).isoformat(),
                    },
                    req_id=req_id,
                )
            )
        wo = state.get("draft_work_order")
        if wo:
            out.append(
                self._msg(
                    "wo_preview",
                    session_id,
                    {
                        "draft_wo": mask_pii_dict(wo),
                        "confidence_score": float(wo.get("confidence_score", 0.0)),
                        "review_record": state.get("review_record"),
                        "risk_flag": wo.get("risk_flag", ""),
                        "actions": ["confirm", "edit", "discard"],
                    },
                    req_id=req_id,
                )
            )
        if state.get("review_record"):
            out.append(self._msg("review_result", session_id, {"review_record": state["review_record"]}, req_id=req_id))
        if status == "DELIVERED" and state.get("hub_ack"):
            out.append(self._msg("hub_ack", session_id, {"ack": state["hub_ack"]}, req_id=req_id))
        elif status == "QUEUED_LOCAL":
            out.append(
                self._msg(
                    "queued_local",
                    session_id,
                    {"wo_number": str(wo.get("wo_number", "")) if wo else "", "next_retry_at": ""},
                    req_id=req_id,
                )
            )
        elif status == "MANUAL_REVIEW":
            out.append(
                self._msg(
                    "manual_review",
                    session_id,
                    {"draft_wo": mask_pii_dict(wo) if wo else {}, "reason": str(state.get("error", "") or "P0_MAX_ROUNDS_EXCEEDED")},
                    req_id=req_id,
                )
            )
        elif status == "FAILED":
            code = "SCHEMA_ERROR" if "schema_error" in str(state.get("error", "")) else "INTERNAL"
            out.append(self._msg("error", session_id, {"code": code, "message": str(state.get("error", ""))}, req_id=req_id))
        return out
```

注意：`config.ws` 字段在 Task 6 才加入 `AppConfig`；本任务测试使用 `AppConfig()` 默认值，需在 Task 6 前让默认 `AppConfig` 含 `ws: WsSettings`——**先跳做 Task 6 的模型字段**（仅 `config.py` 加 `WsSettings` 默认 30/16384/10，不改 yaml），或在本任务直接实现（见 Step 4 说明）。

- [ ] **Step 4: 实现 `WsSettings` 并跑测试**

为避免 `AttributeError: 'AppConfig' object has no attribute 'ws'`，先在 `ako_intake/config.py` 加入（Task 6 会再完善 yaml 读取与端口修正）：

```python
@dataclass
class WsSettings:
    """WS v2 协议参数（设计 3.5.3 ws 段）。"""

    heartbeat_seconds: int = 30
    stream_ack_bytes: int = 16384
    auth_timeout_seconds: int = 10
```

并在 `AppConfig` 中追加字段 `ws: WsSettings = field(default_factory=WsSettings)`，`load_config` 中：

```python
ws_raw = raw.get("ws", {})
ws=WsSettings(
    heartbeat_seconds=int(ws_raw.get("heartbeat_seconds", 30)),
    stream_ack_bytes=int(ws_raw.get("stream_ack_bytes", 16384)),
    auth_timeout_seconds=int(ws_raw.get("auth_timeout_seconds", 10)),
),
```

Run: `python -m pytest tests/test_ws_protocol.py -v`
Expected: PASS（10 passed）

- [ ] **Step 5: 提交**

```bash
git add ako_intake/adapters/ws_protocol.py ako_intake/config.py tests/test_ws_protocol.py
git commit -m "feat(intake): WS v2 协议处理器（白名单/seq/状态事件翻译）"
```

---

### Task 3: app.py WS 端点接入 v2

**Files:**
- Modify: `app.py`（替换 `/ws/intake` 处理器）
- Test: `tests/test_app.py`（更新 `test_ws_intake_roundtrip`，新增 v2 用例）

**Interfaces:**
- Consumes: Task 2 `WsSessionHandler`。
- Produces: `/ws/intake` 端点 v2 化（auth 首消息 + hello；未知 type 回 error）。

- [ ] **Step 1: 写失败测试（更新既有 WS 测试）**

修改 `tests/test_app.py`：

```python
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
            # 事件序：status(PARSING) → status(DELIVERED) → wo_preview → review_result；
            # 须等到 wo_preview 再断言（DELIVERED status 先于其到达）
            if data["type"] == "wo_preview":
                break
            if data["type"] == "status":
                statuses.append(str(data["payload"]["status"]))
        assert "wo_preview" in types
        assert "DELIVERED" in statuses
```

删除旧 `test_ws_intake_roundtrip`。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL（新 v2 用例不通过：旧端点不认 `v`/`payload` 结构）

- [ ] **Step 3: 实现 WS 端点接入**

修改 `app.py`：顶部新增 import 与全局处理器工厂：

```python
from ako_intake.adapters.ws_protocol import WsSessionHandler
from ako_intake.llm.budget import BudgetTracker

budget_tracker = BudgetTracker(config.budget.monthly_quota_tokens)
```

替换 `/ws/intake` 端点：

```python
@app.websocket("/ws/intake")
async def ws_intake(websocket: WebSocket) -> None:
    await websocket.accept()
    handler = WsSessionHandler(config, session_store, queue_store, _graph, metrics, budget_tracker)
    try:
        while True:
            raw = await websocket.receive_text()
            for msg in handler.handle_text(raw):
                await websocket.send_text(msg.model_dump_json(exclude_none=True))
    except WebSocketDisconnect:
        return
```

删除旧端点体内 `intake_input`/`p0_response` 逻辑（v2 处理器接管）。`WebSocketDisconnect` 仍被使用，保留 import；`json` 仅旧端点使用，新端点不再使用，应移除未用 import。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_app.py tests/test_ws_protocol.py -v`
Expected: PASS（全部通过）

- [ ] **Step 5: 提交**

```bash
git add app.py tests/test_app.py
git commit -m "feat(intake): /ws/intake 接入 WS v2 协议处理器"
```

---

### Task 4: bootstrap / 会话 / 队列 / 身份 REST 端点

**Files:**
- Modify: `app.py`（新增端点）、`ako_intake/db/session_store.py`（`list_recent`）、`ako_intake/gateways/identity_client.py`（`login_human`）
- Test: `tests/test_app.py`（新增用例）、`tests/test_session_store.py`（如存在则追加，否则并入 test_app）

**Interfaces:**
- Consumes: Task 1 `BootstrapConfig`、Task 2 `bootstrap_payload`、既有 `queue_store`/`session_store`/`flush_queue`/`HubClient`。
- Produces:
  - `GET /api/v1/bootstrap` → BootstrapConfig 负载
  - `GET /api/v1/intake/sessions` → `{"sessions": [{session_id,status,updated_at}...]}`
  - `POST /api/v1/intake/sessions` body `{raw_text?: str, draft_wo?: dict}` → `{session_id, status, review_record?}`；raw_text 空则仅建 IDLE 会话
  - `POST /api/v1/intake/sessions/{id}/abandon` → `{session_id, status:"ABANDONED"}`；不存在 404
  - `GET /api/v1/intake/queue/stats` → `{pending, done, failed}`
  - `POST /api/v1/intake/queue/flush` → `{flushed: [wo_number...]}`
  - `POST /api/v1/identity/login` body `{account, fingerprint}` → `{token, expires_at, identity}`；identity 未配置返回开发态 `dev-token`
  - `POST /api/v1/identity/verify` body `{token}` → verify_human 结果
  - `SessionStore.list_recent(limit=50) -> list[dict]`
  - `identity_client.login_human(account, fingerprint, base_url="", timeout=10.0) -> dict`

- [ ] **Step 1: 写失败测试**

在 `tests/test_app.py` 追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_app.py -k "bootstrap or sessions or abandon or queue or identity" -v`
Expected: FAIL（404/KeyError）

- [ ] **Step 3: 实现端点与辅助方法**

`ako_intake/db/session_store.py` 追加：

```python
def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
    """最近会话（续传选择页）：非终态全量 + 最近终态。"""
    with closing(self._connect()) as conn:
        rows = conn.execute(
            "SELECT session_id, status, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

`ako_intake/gateways/identity_client.py` 追加：

```python
def login_human(account: str, fingerprint: str, base_url: str = "", timeout: float = 10.0) -> Dict[str, Any]:
    """人类登录（A.5 第一重）。

    base_url 为空时返回开发态令牌（仅非生产，设计 R3）。
    """
    if not base_url:
        return {"ok": True, "token": "dev-token", "human_id": "mock-human", "method": "mock"}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/login",
                json={"account": account, "fingerprint": fingerprint},
            )
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "method": "http"}
```

`app.py` 追加（`from ako_intake.models import Ako1WorkOrder`、`from ako_intake.services.form_builder import validate_work_order`、`from ako_intake.services.reviewer import review_work_order`、`from ako_intake.core.pipeline import flush_queue`、`from ako_intake.gateways.hub_client import HubClient`、`from ako_intake.adapters.ws_protocol import bootstrap_payload` 顶部 import）：

```python
class CreateSessionBody(BaseModel):
    raw_text: Optional[str] = None
    draft_wo: Optional[Dict[str, Any]] = None


class IdentityLoginBody(BaseModel):
    account: str
    fingerprint: str


class IdentityVerifyBody(BaseModel):
    token: str


@app.get("/api/v1/bootstrap")
def bootstrap() -> Dict[str, Any]:
    return bootstrap_payload(config, budget_tracker)


@app.get("/api/v1/intake/sessions")
def list_sessions() -> Dict[str, Any]:
    return {"sessions": session_store.list_recent()}


@app.post("/api/v1/intake/sessions")
def create_session(body: CreateSessionBody) -> Dict[str, Any]:
    session_id = f"sess-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if body.draft_wo is not None:
        draft = {**body.draft_wo}
        # 工单号由系统生成（白皮书 US-003），用户无需填写
        draft.setdefault("wo_number", draft_wo_number(seq=1))
        wo = Ako1WorkOrder.model_validate(draft)
        problems = validate_work_order(wo)
        if problems:
            raise HTTPException(status_code=400, detail="schema_error: " + "; ".join(problems))
        record = review_work_order(wo, config.intake.review_score_threshold)
        state = {
            "session_id": session_id,
            "status": "REVIEWING",
            "raw_input": "[expert]",
            "draft_work_order": wo.model_dump(),
            "review_record": record.model_dump(),
            "clarification_log": [],
            "pending_answers": [],
            "p0_rounds": 0,
            "queue": "main",
        }
        session_store.save(session_id, "REVIEWING", state)
        return {"session_id": session_id, "status": "REVIEWING", "review_record": record.model_dump()}
    state = {
        "session_id": session_id,
        "status": "IDLE",
        "raw_input": body.raw_text or "",
        "clarification_log": [],
        "pending_answers": [],
        "p0_rounds": 0,
        "queue": "main",
    }
    session_store.save(session_id, "IDLE", state)
    return {"session_id": session_id, "status": "IDLE"}


@app.post("/api/v1/intake/sessions/{session_id}/abandon")
def abandon_session(session_id: str) -> Dict[str, Any]:
    state = session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    state["status"] = "ABANDONED"
    session_store.save(session_id, "ABANDONED", state)
    return {"session_id": session_id, "status": "ABANDONED"}


@app.get("/api/v1/intake/queue/stats")
def queue_stats() -> Dict[str, Any]:
    # 空队时 stats() 返回 {}，规范化为三键零值（设计 3.5.2 {pending, done, failed}）
    raw = queue_store.stats()
    return {"pending": raw.get("pending", 0), "done": raw.get("done", 0), "failed": raw.get("failed", 0)}


@app.post("/api/v1/intake/queue/flush")
def queue_flush() -> Dict[str, Any]:
    hub = HubClient(config.gateways.hub_base_url)
    flushed = flush_queue(queue_store, hub, config)
    return {"flushed": flushed}


@app.post("/api/v1/identity/login")
def identity_login(body: IdentityLoginBody) -> Dict[str, Any]:
    result = login_human(body.account, body.fingerprint, config.gateways.identity_base_url)
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail=str(result.get("error", "login failed")))
    return {"token": result["token"], "expires_at": result.get("expires_at", ""), "identity": {"account": body.account}}


@app.post("/api/v1/identity/verify")
def identity_verify(body: IdentityVerifyBody) -> Dict[str, Any]:
    return verify_human(body.token, config.gateways.identity_base_url)
```

`app.py` 顶部补 import：`from typing import Optional`（现有 `Any, Dict` 基础上追加）、`from datetime import datetime`、`from ako_intake.gateways.identity_client import login_human, verify_human`、`from ako_intake.utils.naming import draft_wo_number`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS（含 Task 3 的 v2 WS 用例，全绿）

- [ ] **Step 5: 提交**

```bash
git add app.py ako_intake/db/session_store.py ako_intake/gateways/identity_client.py tests/test_app.py
git commit -m "feat(intake): bootstrap/会话/队列/身份 REST 端点"
```

---

### Task 5: /metrics 增强（budget + queue）

**Files:**
- Modify: `app.py`（`metrics_endpoint`）
- Test: `tests/test_app.py`（追加用例）

**Interfaces:**
- Consumes: Task 3 的 `budget_tracker`、既有 `queue_store.stats()`。
- Produces: `/metrics` 响应增加 `budget`（`usage_by_caller`/`usage_percent`/`monthly_quota_tokens`）与 `queue`（`pending`/`done`/`failed`）。

- [ ] **Step 1: 写失败测试**

```python
def test_metrics_includes_budget_and_queue() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "budget" in body
    assert "usage_percent" in body["budget"]
    assert "queue" in body
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_app.py -k metrics -v`
Expected: FAIL（无 budget/queue 键）

- [ ] **Step 3: 实现**

修改 `app.py`：

```python
@app.get("/metrics")
def metrics_endpoint() -> Dict[str, Any]:
    payload = metrics_payload(metrics, budget=budget_tracker.snapshot())
    payload["queue"] = queue_store.stats()
    return payload
```

（`metrics_payload(metrics, budget)` 现有实现已支持 `budget` 参数并合并到负载。）

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app.py tests/test_app.py
git commit -m "feat(intake): /metrics 并入 budget 与本地队列统计"
```

---

### Task 6: 配置扩展与端口修正

**Files:**
- Modify: `config/intake_config.yaml`（`service.port` → 5026；新增 `ws:` 段）、`ako_intake/config.py`（`load_config` 读取 ws 段）
- Test: `tests/test_config.py`（新建）

**Interfaces:**
- Consumes: Task 2 已加 `WsSettings` 字段。
- Produces: `load_config()` 返回 `config.ws.heartbeat_seconds` 等；默认端口 5026。

- [ ] **Step 1: 写失败测试**

```python
"""配置加载测试（FI-II-07）。"""

from __future__ import annotations

from ako_intake.config import load_config


def test_default_port_is_5026() -> None:
    config = load_config()
    assert config.port == 5026


def test_ws_settings_loaded() -> None:
    config = load_config()
    assert config.ws.heartbeat_seconds >= 1
    assert config.ws.stream_ack_bytes >= 1024
    assert config.ws.auth_timeout_seconds >= 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL（yaml 中 port=5027；ws 段缺失但走默认值，端口用例失败）

- [ ] **Step 3: 实现**

修改 `config/intake_config.yaml` 顶部：

```yaml
service:
  host: "0.0.0.0"
  port: 5026  # 与白皮书 6.6 / docs/API.md 一致（设计附录 B，修正原 5027）
  agent_id: "AKO_hub_intake_agent"
```

并在 `budget:` 段后新增：

```yaml
ws:
  heartbeat_seconds: 30
  stream_ack_bytes: 16384
  auth_timeout_seconds: 10
```

修改 `ako_intake/config.py` `load_config` 中（Task 2 已加 `ws_raw` 读取，核对 `ws_raw.get` 各键与上一致；若 Task 2 未加则补全）：

```python
ws_raw = raw.get("ws", {})
# 并在 AppConfig(...) 调用中加入:
ws=WsSettings(
    heartbeat_seconds=int(ws_raw.get("heartbeat_seconds", 30)),
    stream_ack_bytes=int(ws_raw.get("stream_ack_bytes", 16384)),
    auth_timeout_seconds=int(ws_raw.get("auth_timeout_seconds", 10)),
),
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_config.py tests/test_ws_protocol.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add config/intake_config.yaml ako_intake/config.py tests/test_config.py
git commit -m "fix(intake): 端口统一 5026，新增 ws 协议配置段"
```

---

### Task 7: 契约 schema 导出与防漂移测试

**Files:**
- Create: `scripts/export_contract_schemas.py`、`schemas/ws_message_v2.json`、`schemas/bootstrap_v1.json`
- Test: `tests/test_contract_schemas.py`（新建）

**Interfaces:**
- Consumes: Task 1 `InboundMessage`/`BootstrapConfig`。
- Produces: `schemas/ws_message_v2.json`（入站判别联合 schema）、`schemas/bootstrap_v1.json`（bootstrap schema）；契约测试保证二者与 Pydantic 导出一致（设计 7.2）。

- [ ] **Step 1: 写失败测试**

```python
"""契约 schema 防漂移测试（FI-III-09，设计 7.2）。

schemas/ 文件由 scripts/export_contract_schemas.py 从 Pydantic 模型导出，
本测试保证已提交文件与导出结果一致。
"""

from __future__ import annotations

import json
from pathlib import Path

from ako_intake.models import BootstrapConfig, InboundMessage

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def _regenerate() -> dict[str, object]:
    return {
        "ws_message_v2.json": InboundMessage.model_json_schema(),
        "bootstrap_v1.json": BootstrapConfig.model_json_schema(),
    }


def test_committed_schemas_match_pydantic_export() -> None:
    for name, fresh in _regenerate().items():
        committed = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert committed == fresh, f"{name} 与 Pydantic 导出不一致，请运行 python scripts/export_contract_schemas.py"


def test_ws_schema_has_discriminator() -> None:
    schema = json.loads((SCHEMAS / "ws_message_v2.json").read_text(encoding="utf-8"))
    assert schema.get("discriminator", {}).get("propertyName") == "type"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_contract_schemas.py -v`
Expected: FAIL（缺 schema 文件）

- [ ] **Step 3: 实现导出脚本并生成文件**

创建 `scripts/export_contract_schemas.py`：

```python
"""从 Pydantic 模型导出契约 JSON Schema 到 schemas/（设计 7.2 单一事实源）。"""

from __future__ import annotations

import json
from pathlib import Path

from ako_intake.models import BootstrapConfig, InboundMessage

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def main() -> int:
    exports = {
        "ws_message_v2.json": InboundMessage.model_json_schema(),
        "bootstrap_v1.json": BootstrapConfig.model_json_schema(),
    }
    for name, schema in exports.items():
        target = SCHEMAS / name
        target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

运行生成：`python scripts/export_contract_schemas.py`
Expected: 生成 `schemas/ws_message_v2.json` 与 `schemas/bootstrap_v1.json`

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_contract_schemas.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add scripts/export_contract_schemas.py schemas/ws_message_v2.json schemas/bootstrap_v1.json tests/test_contract_schemas.py
git commit -m "feat(intake): 契约 schema 导出与防漂移测试"
```

---

### Task 8: docs/API.md 更新为 v2 契约

**Files:**
- Modify: `docs/API.md`

**Interfaces:**
- Consumes: 本计划全部端点与消息类型。
- Produces: 与设计文档第三章一致的 API 文档。

- [ ] **Step 1: 重写 docs/API.md**

将 `docs/API.md` 更新为 v2 契约（与 `docs/AKO_hub_intake_frontend_contract_v1.0.0.md` 第三章一致）：保留健康/指标端点说明，新增 WS v2 消息表（入站 10 类、出站 14 类）、新增 REST 端点表（bootstrap/sessions/abandon/queue/stats/flush/identity），并标注旧 `POST /api/v1/intake/review` 保留。

- [ ] **Step 2: 全量回归**

Run: `python -m pytest -v`
Expected: 全部 PASS（18+ 测试文件全绿）

- [ ] **Step 3: 提交**

```bash
git add docs/API.md
git commit -m "docs(intake): API 文档更新为 WS v2 契约"
```

---

## 自审记录

- **Spec 覆盖**：设计 3.1/3.2（Task 1/2/3 消息与白名单）、3.3 seq 快照（Task 2）、3.4 流帧（Task 2 接受 stream_ack，发射器因 `use_llm=false` 暂空，属设计 R2 既定）、3.5 REST（Task 4/5）、3.6 鉴权（Task 4/2 开发态模拟 + registry 未配置不拦截）、第五章时序（Task 2/3/4 对应）、第六章错误码（Task 2 全部落地）、7.2 契约测试（Task 7）、第八章 Phase A 清单（Task 1-8）；前端 Phase B-E 由 Plan 2 承担。
- **偏差说明**：设计 3.2.2 中 `hello.snapshot`（"仅在存在可续传会话时携带"）因连接阶段无 session_id 无法确定会话，改为统一走 `session_resume` → `session_snapshot` 通道（设计自身已定义该通道）；`wo_discard` 语义按设计"放弃当前工单"实现为清空草稿回 IDLE（`session_abandon` 才到 S90）。
- **占位符扫描**：无 TBD/TODO；每个代码步骤均含完整实现。
- **类型一致性**：`WsSessionHandler._msg/next_seq/handle_text` 签名在 Task 2 定义、Task 3 使用一致；`bootstrap_payload` 在 Task 2 定义、Task 4 使用一致；`InboundMessage`/`BootstrapConfig` 在 Task 1 定义、Task 7 使用一致。
