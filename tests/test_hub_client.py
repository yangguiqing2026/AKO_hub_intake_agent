"""Hub 客户端：幂等/熔断/退避。"""

from __future__ import annotations

import pytest

from ako_intake.gateways.hub_client import CircuitBreaker, HubClient, HubUnreachable
from ako_intake.models import Ako1WorkOrder


def _wo() -> Ako1WorkOrder:
    return Ako1WorkOrder(
        wo_number="WO-DRAFT-20260831-001",
        module="AKO_quote_agent",
        action="审计",
        scope="只动校验逻辑",
        rules=["不修改生产环境"],
        prohibitions=["禁止直接修改生产数据库"],
        deliverable="输出审计报告",
        deadline="90分钟",
    )


def test_deliver_success_via_injected_transport() -> None:
    calls: list[tuple[str, dict]] = []

    def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"status": "acknowledged", "wo_number": "WO-HAI-20260831-001", "queue_position": 1}

    client = HubClient(base_url="http://localhost:8080", _post=fake_post)
    ack = client.deliver_wo(_wo())
    assert ack.status == "acknowledged"
    assert calls[0][0] == "/api/v1/hub/wo/deliver"


def test_hub_unreachable_raises() -> None:
    def fake_post(path: str, payload: dict) -> dict:
        raise HubUnreachable("down")

    client = HubClient(base_url="http://localhost:8080", _post=fake_post)
    with pytest.raises(HubUnreachable):
        client.deliver_wo(_wo())


def test_circuit_breaker_opens_after_failures() -> None:
    breaker = CircuitBreaker(max_failures=2, cooldown_seconds=3600)
    assert not breaker.is_open()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open()


def test_deliver_with_retry_eventual_success() -> None:
    attempts = {"n": 0}

    def fake_post(path: str, payload: dict) -> dict:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise HubUnreachable("transient")
        return {"status": "acknowledged", "wo_number": "WO-HAI-20260831-001"}

    client = HubClient(base_url="http://localhost:8080", _post=fake_post)
    ack = client.deliver_with_retry(_wo(), max_retries=5, base_seconds=0, max_seconds=0)
    assert ack.status == "acknowledged"
    assert attempts["n"] == 3

