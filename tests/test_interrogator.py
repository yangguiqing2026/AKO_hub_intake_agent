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


def test_questions_limited_to_three(config) -> None:
    tree = parse_intent("帮我看看报价模块的数据", config.terms)
    report = detect_ambiguities(tree)
    questions = build_questions(report, round_no=1, max_questions=3)
    assert len(questions) <= 3
    assert all(isinstance(q, Question) for q in questions)


def test_apply_answers_resolves_action_and_scope(config) -> None:
    tree = parse_intent("帮我看看报价模块的数据", config.terms)
    report = detect_ambiguities(tree)
    questions = build_questions(report, 1, 3)
    answers = [
        Answer(qid=questions[0].qid, value="审计"),
        Answer(qid=questions[1].qid, value="只动报价校验逻辑，不动数据库"),
    ]
    updated = apply_answers(tree, answers)
    assert updated.entity_value("action") == "审计"
    assert updated.entity_value("scope") == "只动报价校验逻辑，不动数据库"
    assert not still_unresolved(updated), "澄清后不应再要求 P0"


def test_build_log_entry_round_number() -> None:
    entry = build_log_entry(2, [], [Answer(qid="q-2-action", value="审计")])
    assert entry.round == 2
    assert entry.answers[0].value == "审计"

