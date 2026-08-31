"""流水线编排与本地队列兜底。"""

from __future__ import annotations

from ako_intake.core.pipeline import deliver_with_local_queue, flush_queue, run_full
from ako_intake.db.queue_store import QueueStore
from ako_intake.gateways.hub_client import HubClient, HubUnreachable


def test_run_full_delivered(config) -> None:
    state = run_full("修复报价模块的bug，只动校验逻辑，不动数据库", "sess-p", config)
    assert state["status"] == "DELIVERED"
    assert state["draft_work_order"]["module"] == "AKO_quote_agent"


def test_deliver_local_queue_on_hub_down(config, tmp_path) -> None:
    state = run_full("修复报价模块的bug，只动校验逻辑，不动数据库", "sess-q", config)

    def failing_post(path: str, payload: dict) -> dict:
        raise HubUnreachable("down")

    client = HubClient(base_url="http://localhost:8080", _post=failing_post)
    store = QueueStore(tmp_path / "pending.db")
    result = deliver_with_local_queue(state, config, client, store)
    assert result["status"] == "QUEUED_LOCAL"
    assert store.stats().get("pending", 0) == 1


def test_flush_queue_marks_failed_after_max_retries(config, tmp_path) -> None:
    config.intake.delivery_max_retries = 1
    state = run_full("修复报价模块的bug，只动校验逻辑，不动数据库", "sess-f", config)

    def failing_post(path: str, payload: dict) -> dict:
        raise HubUnreachable("down")

    client = HubClient(base_url="http://localhost:8080", _post=failing_post)
    store = QueueStore(tmp_path / "pending.db")
    store.enqueue(state["draft_work_order"]["wo_number"], state["draft_work_order"])
    flush_queue(store, client, config)
    flush_queue(store, client, config)
    assert store.stats().get("failed", 0) == 1


def test_flush_queue_success(config, tmp_path) -> None:
    state = run_full("修复报价模块的bug，只动校验逻辑，不动数据库", "sess-s", config)

    def ok_post(path: str, payload: dict) -> dict:
        return {"status": "acknowledged", "wo_number": payload["wo_number"]}

    client = HubClient(base_url="http://localhost:8080", _post=ok_post)
    store = QueueStore(tmp_path / "pending.db")
    store.enqueue(state["draft_work_order"]["wo_number"], state["draft_work_order"])
    flushed = flush_queue(store, client, config)
    assert flushed == [state["draft_work_order"]["wo_number"]]
    assert store.stats().get("done", 0) == 1

