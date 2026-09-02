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
from ako_intake.utils.naming import unique_session_id
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
        # 预算软熔断状态 latch（每连接）：None=未初始化，True/False=上次已通知的状态
        self._soft_break_told: Optional[bool] = None

    # ---- 序号与消息构造 ----

    def next_seq(self, session_id: str) -> int:
        seq = self._seqs.get(session_id, 0) + 1
        self._seqs[session_id] = seq
        return seq

    def _msg(self, type_: str, session_id: str, payload: Optional[Dict[str, Any]] = None, req_id: str = "", seq: Optional[int] = None) -> OutboundMessage:
        return OutboundMessage(
            type=type_,
            req_id=req_id,
            session_id=session_id,
            seq=self.next_seq(session_id) if seq is None else seq,
            ts=datetime.now().isoformat(),
            payload=payload or {},
        )

    def _err(self, code: str, message: str, req_id: str = "") -> OutboundMessage:
        return self._msg("error", "", {"code": code, "message": message}, req_id=req_id)

    def _append_soft_break_transition(self, out: List[OutboundMessage]) -> None:
        """入站消息成功处理后轮询预算软熔断状态沿（设计：每连接 latch，非消费式）。

        budget 未注入（None）时跳过；当前态 = should_soft_break(soft_limit_percent)。
        - 与上次通知态不同 → 追加 soft_break 消息（active 表示当前态）并翻转 latch；
        - 首次轮询（latch 为 None）：active=true 直接发射（覆盖 auth 后、首次业务消息前的跨界），
          active=false 仅初始化，避免连接建立时对每个空闲连接广播无沿状态。
        """
        if self.budget is None:
            return
        active = bool(self.budget.should_soft_break(self.config.budget.soft_limit_percent))
        if self._soft_break_told == active:
            return
        if self._soft_break_told is None and not active:
            self._soft_break_told = False
            return
        self._soft_break_told = active
        out.append(
            self._msg(
                "soft_break",
                "",
                {
                    "usage_percent": self.budget.usage_percent(),
                    "monthly_quota_tokens": self.budget.monthly_quota_tokens,
                    "active": active,
                },
            )
        )

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
            out = handler(msg)
            # 软熔断沿检测挂入站消息响应尾部；auth 已由 hello.bootstrap 快照对账，跳过避免重复
            if msg_type != "auth":
                self._append_soft_break_transition(out)
            return out
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
        session_id = msg.session_id or unique_session_id()  # 微秒+计数器防碰撞（基线 flaky 修复）
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
        state["human_confirmed"] = False  # 草稿变更即作废旧的人工确认（M07 门禁防绕过）
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
        seq = self.next_seq(session_id)
        return [
            self._msg(
                "session_snapshot",
                session_id,
                {"state": mask_pii_dict(state), "seq": seq},
                req_id=msg.req_id,
                seq=seq,
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
        # 携带 session_id 时沿该会话 seq 计数（终审 C1 测试要求快照后 seq 连续）
        return [self._msg("pong", msg.session_id or "", {}, req_id=msg.req_id)]

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
