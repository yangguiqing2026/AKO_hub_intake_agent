"""流水线编排：图调用 + 本地队列兜底。"""

from __future__ import annotations

from typing import Any, Dict, List

from ako_intake.config import AppConfig
from ako_intake.core.graph import compile_graph
from ako_intake.core.state import IntakeState
from ako_intake.db.queue_store import QueueStore
from ako_intake.gateways.hub_client import HubClient, HubUnreachable
from ako_intake.models import Ako1WorkOrder


def run_full(raw_text: str, session_id: str, config: AppConfig) -> Dict[str, Any]:
    """执行完整 intake 流水线（解析→歧义→生成→评审→投递/人工）。"""
    graph = compile_graph(config)
    initial: IntakeState = {
        "session_id": session_id,
        "status": "PARSING",
        "raw_input": raw_text,
        "clarification_log": [],
        "pending_answers": [],
        "p0_rounds": 0,
        "queue": "main",
    }
    return graph.invoke(initial)


def run_parse_detect(raw_text: str, config: AppConfig) -> Dict[str, Any]:
    """仅执行解析与歧义检测（供看板即时反馈）。"""
    state = run_full(raw_text, "preview", config)
    return state


def deliver_with_local_queue(
    state: Dict[str, Any],
    config: AppConfig,
    hub_client: HubClient,
    queue_store: QueueStore,
) -> Dict[str, Any]:
    """投递；Hub 不可达时入本地队列（eventual，零丢失）。"""
    wo = Ako1WorkOrder.model_validate(state["draft_work_order"])
    try:
        ack = hub_client.deliver_wo(wo)
        state["hub_ack"] = ack.model_dump()
        state["status"] = "DELIVERED"
    except HubUnreachable:
        queue_store.enqueue(wo.wo_number, wo.to_payload())
        state["status"] = "QUEUED_LOCAL"
        state["queue"] = "local"
    return state


def flush_queue(
    queue_store: QueueStore,
    hub_client: HubClient,
    config: AppConfig,
    limit: int = 10,
) -> List[str]:
    """冲刷本地队列（指数退避，超限标记失败）。"""
    flushed: List[str] = []
    for item in queue_store.peek_due()[:limit]:
        wo_number = item["wo_number"]
        payload = item["payload_json"]
        attempts = item["attempts"]
        try:
            hub_client.deliver_raw(payload)
            queue_store.mark_success(wo_number)
            flushed.append(wo_number)
        except HubUnreachable:
            if attempts >= config.intake.delivery_max_retries:
                queue_store.mark_failed(wo_number)
            else:
                backoff = QueueStore.compute_backoff(
                    attempts + 1,
                    config.intake.retry_base_seconds,
                    config.intake.retry_max_seconds,
                )
                from datetime import datetime, timedelta

                next_retry = (datetime.now() + timedelta(seconds=backoff)).isoformat()
                queue_store.mark_attempt(wo_number, next_retry)
    return flushed

