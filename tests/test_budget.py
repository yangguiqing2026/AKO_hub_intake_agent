"""预算软熔断（FI-IV-04）。"""

from __future__ import annotations

from ako_intake.llm.budget import BudgetTracker


def test_soft_break_at_quota_percent() -> None:
    tracker = BudgetTracker(monthly_quota_tokens=100_000)
    tracker.record("session-a", 5_000)
    assert tracker.usage_percent() == 5.0
    assert tracker.should_soft_break(limit_percent=5.0)


def test_usage_recorded_per_caller() -> None:
    tracker = BudgetTracker(monthly_quota_tokens=100_000)
    tracker.record("a", 100)
    tracker.record("a", 50)
    tracker.record("b", 10)
    assert tracker.usage("a") == 150
    assert tracker.snapshot()["usage_by_caller"]["b"] == 10


def test_set_quota_lowers_usage_percent() -> None:
    """配额上调（解除软熔断的唯一进程内途径）：usage_percent 随新配额回落。"""
    tracker = BudgetTracker(monthly_quota_tokens=100_000)
    tracker.record("x", 5_000)
    assert tracker.usage_percent() == 5.0
    assert tracker.should_soft_break(limit_percent=5.0)
    tracker.set_quota(1_000_000)
    assert tracker.usage_percent() == 0.5
    assert not tracker.should_soft_break(limit_percent=5.0)
    assert tracker.snapshot()["monthly_quota_tokens"] == 1_000_000

