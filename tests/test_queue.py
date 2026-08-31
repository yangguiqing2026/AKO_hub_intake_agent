"""本地投递队列：零丢失 + 指数退避。"""

from __future__ import annotations

import json

from ako_intake.db.queue_store import QueueStore
from ako_intake.gateways.hub_client import HubClient, HubUnreachable
from ako_intake.models import Ako1WorkOrder


def _queue(tmp_path) -> QueueStore:
    return QueueStore(tmp_path / "pending.db")


def _wo_payload() -> str:
    wo = Ako1WorkOrder(
        wo_number="WO-HAI-20260831-001",
        module="AKO_quote_agent",
        action="审计",
        scope="只动校验逻辑",
        rules=["不修改生产环境"],
        prohibitions=["禁止直接修改生产数据库"],
        deliverable="输出审计报告",
        deadline="90分钟",
    )
    return json.dumps(wo.to_payload(), ensure_ascii=False)


def test_enqueue_and_peek(tmp_path) -> None:
    store = _queue(tmp_path)
    store.enqueue("WO-HAI-20260831-001", json.loads(_wo_payload()))
    items = store.peek_due()
    assert len(items) == 1
    assert items[0]["wo_number"] == "WO-HAI-20260831-001"


def test_zero_loss_until_success(tmp_path) -> None:
    store = _queue(tmp_path)
    store.enqueue("WO-HAI-20260831-002", json.loads(_wo_payload()))

    def failing_post(path: str, payload: dict) -> dict:
        raise HubUnreachable("down")

    client = HubClient(base_url="http://localhost:8080", _post=failing_post)
    for _ in range(3):
        for item in store.peek_due():
            try:
                client.deliver_raw(item["payload_json"])
                store.mark_success(item["wo_number"])
            except HubUnreachable:
                store.mark_attempt(item["wo_number"], None)
    remaining = [i for i in store.peek_due() if i["status"] == "pending"]
    assert store.stats().get("pending", 0) == 1, "Hub 未恢复前工单不得丢失"
    assert remaining


def test_compute_backoff_capped() -> None:
    assert QueueStore.compute_backoff(1, 60, 600) == 60
    assert QueueStore.compute_backoff(4, 60, 600) == 480
    assert QueueStore.compute_backoff(5, 60, 600) == 600  # 封顶
