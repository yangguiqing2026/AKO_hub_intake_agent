"""事件上报客户端（hub :8080 /events）。"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger("ako_intake.events")


def publish_event(
    event_type: str,
    agent_id: str,
    data: Optional[Dict[str, Any]] = None,
    hub_base_url: str = "",
    transport: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
) -> bool:
    """发布事件到 hub；未配置地址时为本地记录（测试/离线模式）。"""
    payload = {"type": event_type, "agent_id": agent_id, "data": data or {}}
    if not hub_base_url:
        logger.info("事件本地记录（hub 未配置）: %s", event_type)
        return True
    try:
        if transport is not None:
            transport("/events", payload)
            return True
        with httpx.Client(timeout=10.0) as client:
            response = client.post(f"{hub_base_url.rstrip('/')}/events", json=payload)
            response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("事件上报失败: %s", exc)
        return False

