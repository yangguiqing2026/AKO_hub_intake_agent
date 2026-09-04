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

# ── 动作词表（2026-09-03 修复：按目标 module 补全业务动词） ──────────
# 背景：quote 域请求（“外墙板的报价”）曾因 action 选项/词面不含“报价”
# 导致 P0 多轮无法收敛 → 误转人工并显示误导性 P0_MAX_ROUNDS_EXCEEDED。
BASE_ACTION_OPTIONS = ["审计", "修复", "优化", "设计", "审查"]
MODULE_ACTION_EXTRAS: dict = {
    "quote": ["报价", "预算"],
    "law": ["起草", "审查"],
    "writer": ["写作", "修改"],
}
ACTION_SYNONYMS: dict = {
    "报价": ["报价", "算价", "计价", "出报价", "报个价"],
    "预算": ["预算", "成本预算"],
}


def module_action_options(module_value: str = "") -> List[str]:
    """按目标 module 返回 action 选项（业务动词前置 + 基础集去重）。"""
    extras: List[str] = []
    mv = (module_value or "").lower()
    for key, verbs in MODULE_ACTION_EXTRAS.items():
        if key in mv:
            extras.extend(verbs)
    seen, out = set(), []
    for v in extras + BASE_ACTION_OPTIONS:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def normalize_action_value(value: str) -> str:
    """自由文本答复→规范动作值（含词/近义词命中）。"""
    v = str(value or "").strip()
    if not v:
        return v
    for canonical, keys in ACTION_SYNONYMS.items():
        if any(k in v for k in keys):
            return canonical
    return v


def build_questions(report: AmbiguityReport, round_no: int, max_questions: int = 3) -> List[Question]:
    """生成自然语言反问（2026-09-04 交互改造：一问一答，替代多卡片表单）。

    - 每轮只取第一个*必答*歧义项，用自然语言问句推进对话；
    - 非必答项（rules/deliverable/deadline 缺省推断）不再打扰，走默认值；
    - action 问题附业务动词提示语（仍接受自然语言答复，同义词归一）。
    """
    for item in first_questions(report, max_questions):
        if not item.required_clarification or item.field in ("rules", "deliverable", "deadline"):
            continue  # 缺省可推断项不问，交给默认值
        if item.field == "action":
            return [
                Question(
                    qid=f"q-{round_no}-action",
                    field="action",
                    text="您说的动作具体是？",
                    type="single_choice",
                    options=list(BASE_ACTION_OPTIONS),
                    required=True,
                )
            ]
        if item.field == "scope":
            return [
                Question(
                    qid=f"q-{round_no}-scope",
                    field="scope",
                    text="这次任务的范围是什么？（只做____、不动____，请用一句话说明）",
                    type="open",
                    options=[],
                    required=True,
                )
            ]
        return [
            Question(
                qid=f"q-{round_no}-{item.field}",
                field=item.field,
                text=f"「{item.field}」还不清楚，请补充说明：",
                type="open",
                options=[],
                required=True,
            )
        ]
    return []


def apply_answers(intent_tree: IntentTree, answers: List[Answer]) -> IntentTree:
    """将用户答复回填意图树。"""
    updated = intent_tree.model_copy(deep=True)
    for answer in answers:
        if answer.qid.endswith("-action"):
            value = normalize_action_value(answer.value)
            updated.action_candidates = [value]
            updated.entities = [
                e for e in updated.entities if e.type != "action"
            ] + [Entity(type="action", value=value, confidence=1.0)]
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

