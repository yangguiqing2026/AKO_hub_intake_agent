"""M03 P0 Interrogator：反向提问与轮次管理。"""

from __future__ import annotations

from datetime import datetime
from typing import List

from ako_intake.models import (
    AmbiguityReport,
    Answer,
    ClarificationLogEntry,
    Entity,
    IntentTree,
    Question,
)
from ako_intake.services.ambiguity_detector import detect_ambiguities, first_questions


def build_questions(report: AmbiguityReport, round_no: int, max_questions: int = 3) -> List[Question]:
    """生成反问卡片（每轮最多 3 问）。"""
    questions: List[Question] = []
    for item in first_questions(report, max_questions):
        if item.field == "action":
            questions.append(
                Question(
                    qid=f"q-{round_no}-action",
                    field="action",
                    text="您说的动作具体是？",
                    type="single_choice",
                    options=["审计", "修复", "优化", "设计", "审查"],
                    required=True,
                )
            )
        elif item.field == "scope":
            questions.append(
                Question(
                    qid=f"q-{round_no}-scope",
                    field="scope",
                    text="请明确范围（只动____，不动____）：",
                    type="open",
                    options=[],
                    required=True,
                )
            )
        else:
            questions.append(
                Question(
                    qid=f"q-{round_no}-{item.field}",
                    field=item.field,
                    text=f"「{item.field}」未声明，采用默认推断是否可接受？",
                    type="confirm",
                    options=["接受默认", "自定义"],
                    required=False,
                )
            )
    return questions


def apply_answers(intent_tree: IntentTree, answers: List[Answer]) -> IntentTree:
    """将用户答复回填意图树。"""
    updated = intent_tree.model_copy(deep=True)
    for answer in answers:
        if answer.qid.endswith("-action"):
            updated.action_candidates = [answer.value]
            updated.entities = [
                e for e in updated.entities if e.type != "action"
            ] + [Entity(type="action", value=answer.value, confidence=1.0)]
        elif answer.qid.endswith("-scope"):
            updated.entities = [
                e for e in updated.entities if e.type != "scope"
            ] + [Entity(type="scope", value=answer.value, confidence=1.0)]
    return updated


def build_log_entry(round_no: int, questions: List[Question], answers: List[Answer]) -> ClarificationLogEntry:
    """构造澄清记录条目。"""
    return ClarificationLogEntry(
        round=round_no,
        questions=questions,
        answers=answers,
        timestamp=datetime.now().isoformat(),
    )


def still_unresolved(intent_tree: IntentTree, threshold: float = 0.7) -> bool:
    """答复后是否仍有待澄清歧义。"""
    return detect_ambiguities(intent_tree, threshold).needs_clarification(threshold)

