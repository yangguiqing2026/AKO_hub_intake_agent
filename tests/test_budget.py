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

