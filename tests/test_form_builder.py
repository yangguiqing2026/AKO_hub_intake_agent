"""M04 工单生成：8 字段完整 + Schema。"""

from __future__ import annotations

from ako_intake.config import IntakeSettings
from ako_intake.models import ClarificationLogEntry
from ako_intake.services.form_builder import build_work_order, validate_work_order
from ako_intake.services.interrogator import build_log_entry
from ako_intake.services.nlu_parser import parse_intent
from ako_intake.utils.naming import draft_wo_number, validate_wo_number


def _resolved_tree(config):
    tree = parse_intent("修复报价模块的bug，只动校验逻辑，不动数据库", config.terms)
    return tree


def test_eight_fields_filled(config) -> None:
    tree = _resolved_tree(config)
    log: list[ClarificationLogEntry] = [
        build_log_entry(1, [], [])
    ]
    wo = build_work_order(tree, log, IntakeSettings(), session_id="sess-1", seq=1)
    assert wo.wo_number.startswith("WO-DRAFT-")
    assert wo.module == "AKO_quote_agent"
    assert wo.action == "修复"
    assert wo.scope == "只动校验逻辑"
    assert wo.rules and wo.prohibitions and wo.deliverable and wo.deadline
    assert validate_work_order(wo) == []


def test_conservative_default_when_ambiguous(config) -> None:
    tree = parse_intent("报价模块的数据", config.terms)
    wo = build_work_order(tree, [], IntakeSettings(), session_id="sess-2", seq=2)
    assert wo.action == "审签"  # 最保守策略
    assert "不动任何代码/数据" in wo.scope


def test_draft_wo_number_format() -> None:
    number = draft_wo_number(now="20260831", seq=7)
    assert number == "WO-DRAFT-20260831-007"
    assert validate_wo_number(number)
    assert not validate_wo_number("WO-X-20260831-1")
