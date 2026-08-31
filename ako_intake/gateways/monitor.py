"""健康与指标负载（FI-IV-05）。"""

from __future__ import annotations

from typing import Any, Dict

from ako_intake.services.observability import Metrics


def health_payload(deps: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """/health 负载。"""
    ok = all(item.get("ok", False) for item in deps.values()) if deps else True
    return {"status": "ok" if ok else "degraded", "deps": deps}


def metrics_payload(metrics: Metrics, budget: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """/metrics 负载。"""
    payload: Dict[str, Any] = metrics.snapshot()
    if budget:
        payload["budget"] = budget
    return payload

