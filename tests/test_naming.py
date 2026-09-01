"""命名铁律与唯一编号测试。"""
from __future__ import annotations

from ako_intake.utils.naming import unique_draft_wo_number, validate_wo_number


def test_unique_draft_wo_number_matches_pattern() -> None:
    assert validate_wo_number(unique_draft_wo_number())


def test_unique_draft_wo_number_differs_across_calls() -> None:
    assert unique_draft_wo_number() != unique_draft_wo_number()
