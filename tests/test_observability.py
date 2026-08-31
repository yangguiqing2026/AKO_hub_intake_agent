"""观测指标与监控负载。"""

from __future__ import annotations

from ako_intake.gateways.monitor import health_payload, metrics_payload
from ako_intake.services.observability import Metrics


def test_metrics_snapshot() -> None:
    metrics = Metrics()
    metrics.increment("sessions_total")
    metrics.increment("p0_rounds_total", 2)
    snapshot = metrics.snapshot()
    assert snapshot["sessions_total"] == 1
    assert snapshot["p0_rounds_total"] == 2


def test_health_and_metrics_payloads() -> None:
    metrics = Metrics()
    payload = metrics_payload(metrics, budget={"usage_percent": 1.2})
    assert payload["budget"]["usage_percent"] == 1.2
    assert health_payload({"hub": {"ok": True}})["status"] == "ok"
    assert health_payload({"hub": {"ok": False}})["status"] == "degraded"

