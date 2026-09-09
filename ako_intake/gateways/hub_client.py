"""Hub 投递客户端（M06：幂等 + 熔断 + 指数退避）。"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, Optional

import httpx

from ako_intake.db.queue_store import QueueStore
from ako_intake.models import Ako1WorkOrder, HubAck


class HubUnreachable(Exception):
    """Hub 不可达异常。"""


class CircuitBreaker:
    """熔断器（FI-III-05）。"""

    def __init__(self, max_failures: int = 3, cooldown_seconds: float = 60.0) -> None:
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            return time.monotonic() - self._opened_at < self.cooldown_seconds

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.max_failures:
                self._opened_at = time.monotonic()

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None


class HubClient:
    """Hub REST 客户端。_post 可注入（测试/模拟传输）。"""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 10.0,
        breaker: Optional[CircuitBreaker] = None,
        _post: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.breaker = breaker or CircuitBreaker()
        self._post = _post

    def _request(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.breaker.is_open():
            raise HubUnreachable("熔断器开启，拒绝请求")
        if self._post is not None:
            try:
                result = self._post(path, payload)
                self.breaker.record_success()
                return result
            except HubUnreachable:
                self.breaker.record_failure()
                raise
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}{path}",
                    json=payload,
                    headers={"X-Intake-Agent-Key": self.api_key} if self.api_key else {},
                )
                response.raise_for_status()
                self.breaker.record_success()
                return response.json()
        except Exception as exc:
            self.breaker.record_failure()
            raise HubUnreachable(str(exc)) from exc

    def allocate_wo(self, draft_wo_number: str, module: str, action: str) -> HubAck:
        result = self._request(
            "/api/v1/hub/wo/allocate",
            {"draft_wo_number": draft_wo_number, "module": module, "action": action},
        )
        return HubAck.model_validate(result)

    def deliver_wo(self, wo: Ako1WorkOrder, extra: Optional[Dict[str, Any]] = None) -> HubAck:
        """投递正式工单；extra 为随工单透传的附加字段（2026-09-09：
        writer.topic / quote.raw_input——hub 服务端原样存 raw_payload）。"""
        payload = wo.to_payload()
        if extra:
            payload.update(extra)
        result = self._request("/api/v1/hub/wo/deliver", payload)
        return HubAck.model_validate(result)

    def deliver_raw(self, payload_json: str) -> HubAck:
        """按队列持久化载荷原样投递（含透传字段，不过 model 过滤丢字段）。"""
        payload = json.loads(payload_json)
        result = self._request("/api/v1/hub/wo/deliver", payload)
        return HubAck.model_validate(result)

    def deliver_with_retry(
        self,
        wo: Ako1WorkOrder,
        max_retries: int = 10,
        base_seconds: int = 60,
        max_seconds: int = 600,
    ) -> HubAck:
        """指数退避重试投递。"""
        last_error: Optional[HubUnreachable] = None
        for attempt in range(1, max_retries + 1):
            try:
                return self.deliver_wo(wo)
            except HubUnreachable as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(QueueStore.compute_backoff(attempt, base_seconds, max_seconds))
        raise HubUnreachable(f"投递失败，已重试 {max_retries} 次: {last_error}")

