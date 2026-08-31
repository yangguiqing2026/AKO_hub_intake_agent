"""依赖探测（cluster_guardian /health 使用）。"""

from __future__ import annotations

import time
from typing import Any, Dict

import httpx

from ako_intake.config import AppConfig


def probe_url(name: str, url: str, timeout: float = 2.0) -> Dict[str, Any]:
    """探测单个端点。"""
    started = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{url.rstrip('/')}/health")
            response.raise_for_status()
        ok = True
    except Exception:
        ok = False
    return {
        "name": name,
        "ok": ok,
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
    }


def probe_all(config: AppConfig) -> Dict[str, Dict[str, Any]]:
    """探测全部依赖。"""
    targets = {
        "hub": config.gateways.hub_base_url,
        "registry": config.gateways.registry_base_url,
        "identity": config.gateways.identity_base_url,
        "knowledge": config.knowledge_base_url if config.knowledge_enabled else "",
    }
    return {
        name: probe_url(name, url)
        for name, url in targets.items()
        if url
    }

