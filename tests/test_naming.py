"""命名铁律与唯一编号测试。"""
from __future__ import annotations

from ako_intake.utils.naming import unique_draft_wo_number, unique_session_id, validate_wo_number


def test_unique_draft_wo_number_matches_pattern() -> None:
    assert validate_wo_number(unique_draft_wo_number())


def test_unique_draft_wo_number_differs_across_calls() -> None:
    assert unique_draft_wo_number() != unique_draft_wo_number()


def test_unique_session_id_differs_across_calls() -> None:
    """会话 ID 防碰撞：连续两次调用必不同（基线 flaky 修复）。"""
    assert unique_session_id() != unique_session_id()


def test_unique_session_id_prefix() -> None:
    assert unique_session_id().startswith("sess-")
