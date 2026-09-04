"""M03 P0 反问引擎。"""

from __future__ import annotations

from ako_intake.models import Answer, Question
from ako_intake.services.ambiguity_detector import detect_ambiguities
from ako_intake.services.interrogator import (
    apply_answers,
    build_log_entry,
    build_questions,
    still_unresolved,
)
from ako_intake.services.nlu_parser import parse_intent


def test_questions_limited_to_one_per_round(config) -> None:
    """2026-09-04 交互改造：一问一答，每轮至多 1 个必答自然语言问句。"""
    tree = parse_intent("帮我看看报价模块的数据", config.terms)
    report = detect_ambiguities(tree)
    questions = build_questions(report, round_no=1, max_questions=3)
    assert len(questions) == 1
    assert all(isinstance(q, Question) for q in questions)
    assert questions[0].required


def test_apply_answers_resolves_action_and_scope_sequentially(config) -> None:
    tree = parse_intent("帮我看看报价模块的数据", config.terms)
    report = detect_ambiguities(tree)
    # 第一轮：action 一问
    q1 = build_questions(report, 1, 3)[0]
    assert q1.field == "action"
    updated = apply_answers(tree, [Answer(qid=q1.qid, value="审计")])
    assert updated.entity_value("action") == "审计"
    # 第二轮：scope 一问（逐项推进，未答项不重问）
    report2 = detect_ambiguities(updated)
    q2 = build_questions(report2, 2, 3)[0]
    assert q2.field == "scope"
    updated2 = apply_answers(updated, [Answer(qid=q2.qid, value="只动报价校验逻辑，不动数据库")])
    assert updated2.entity_value("scope") == "只动报价校验逻辑，不动数据库"
    assert not still_unresolved(updated2), "澄清后不应再要求 P0"


def test_build_log_entry_round_number() -> None:
    entry = build_log_entry(2, [], [Answer(qid="q-2-action", value="审计")])
    assert entry.round == 2
    assert entry.answers[0].value == "审计"

