"""观测指标（FI-II-08 / FI-IV-05）。"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """进程内指标。"""

    sessions_total: int = 0
    p0_rounds_total: int = 0
    delivered_total: int = 0
    failed_total: int = 0
    tokens_total: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + amount)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "sessions_total": self.sessions_total,
                "p0_rounds_total": self.p0_rounds_total,
                "delivered_total": self.delivered_total,
                "failed_total": self.failed_total,
                "tokens_total": self.tokens_total,
            }

