"""事件上报。"""

from __future__ import annotations

from ako_intake.adapters.events import publish_event


def test_publish_local_when_hub_not_configured() -> None:
    assert publish_event("wo_delivered", "AKO_hub_intake_agent", hub_base_url="") is True


def test_publish_via_transport() -> None:
    captured: list[tuple[str, dict]] = []

    def transport(path: str, payload: dict) -> dict:
        captured.append((path, payload))
        return {"status": "ENQUEUED"}

    ok = publish_event("wo_delivered", "AKO_hub_intake_agent", {"wo": "1"}, hub_base_url="http://localhost:8080", transport=transport)
    assert ok
    assert captured[0][0] == "/events"
    assert captured[0][1]["type"] == "wo_delivered"

