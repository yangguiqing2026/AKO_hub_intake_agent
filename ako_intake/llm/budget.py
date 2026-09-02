"""Token 记账与预算软熔断（FI-IV-04）。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class BudgetTracker:
    """按会话与调用方记录 Token 消耗。"""

    monthly_quota_tokens: int = 1_000_000
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _usage: dict[str, int] = field(default_factory=dict)

    def record(self, caller: str, tokens: int) -> None:
        """记录 Token 消耗。"""
        with self._lock:
            self._usage[caller] = self._usage.get(caller, 0) + max(0, tokens)

    def usage(self, caller: str) -> int:
        """查询指定调用方消耗。"""
        with self._lock:
            return self._usage.get(caller, 0)

    def usage_percent(self) -> float:
        """当月总消耗占比（%）。"""
        total = sum(self._usage.values())
        if self.monthly_quota_tokens <= 0:
            return 0.0
        return round(total * 100.0 / self.monthly_quota_tokens, 2)

    def set_quota(self, monthly_quota_tokens: int) -> None:
        """调整月配额（上调即解除软熔断的唯一进程内途径）。"""
        with self._lock:
            self.monthly_quota_tokens = max(1, monthly_quota_tokens)

    def should_soft_break(self, limit_percent: float = 5.0) -> bool:
        """是否触发预算软熔断（月配额占比达到阈值）。"""
        return self.usage_percent() >= limit_percent

    def snapshot(self) -> dict[str, object]:
        """指标快照。"""
        return {
            "usage_by_caller": dict(self._usage),
            "usage_percent": self.usage_percent(),
            "monthly_quota_tokens": self.monthly_quota_tokens,
        }

