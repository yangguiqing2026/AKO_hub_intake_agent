"""M04 Form Builder：意图树 → ako1 工单（8 刚性字段）。"""

from __future__ import annotations

from datetime import datetime
from typing import List

from ako_intake.config import IntakeSettings
from ako_intake.models import Ako1WorkOrder, ClarificationLogEntry, IntentTree
from ako_intake.utils.naming import draft_wo_number

DEFAULT_RULES: List[str] = ["不修改生产环境", "Git版本控制", "关键模块人工Review"]
DEFAULT_PROHIBITIONS: List[str] = ["禁止直接修改生产数据库"]

DELIVERABLE_BY_ACTION: dict[str, str] = {
    "审计": "输出审计报告，标注异常数据条目",
    "修复": "输出修复报告 + PR 链接",
    "优化": "输出优化方案与前后对比",
    "设计": "输出设计方案与技术文档",
    "审查": "输出审查报告",
    "生成": "输出生成产物与说明",
    "查看": "输出状态摘要",
}


def _answer_value(log: List[ClarificationLogEntry], field: str) -> str:
    """从澄清记录中查找字段答复。"""
    for entry in log:
        for answer in entry.answers:
            if answer.qid.endswith(f"-{field}") or answer.qid.endswith("-action") and field == "action":
                return answer.value
    return ""


def build_work_order(
    intent_tree: IntentTree,
    clarification_log: List[ClarificationLogEntry],
    settings: IntakeSettings,
    session_id: str,
    seq: int = 1,
) -> Ako1WorkOrder:
    """构建标准 ako1 工单。"""
    module = intent_tree.entity_value("module") or "AKO_hub_agent"
    action = _answer_value(clarification_log, "action") or (
        intent_tree.action_candidates[0] if intent_tree.action_candidates else "审签"
    )
    scope = _answer_value(clarification_log, "scope") or intent_tree.entity_value("scope") or "全局审计，不动任何代码/数据"
    deadline = _answer_value(clarification_log, "deadline") or f"{settings.default_deadline_minutes}分钟"
    deliverable = DELIVERABLE_BY_ACTION.get(action, "输出执行结果与报告")
    wo = Ako1WorkOrder(
        wo_number=draft_wo_number(seq=seq),
        module=module,
        action=action,
        scope=scope,
        rules=list(DEFAULT_RULES),
        prohibitions=list(DEFAULT_PROHIBITIONS),
        deliverable=deliverable,
        deadline=deadline,
        intake_session_id=session_id,
        clarification_rounds=len(clarification_log),
        confidence_score=0.95 if intent_tree.entity_value("module") else 0.6,
    )
    return wo


def validate_work_order(wo: Ako1WorkOrder) -> List[str]:
    """Schema/完整性校验，返回问题列表（空=通过）。"""
    problems: List[str] = []
    if not wo.module:
        problems.append("module 为空")
    if not wo.action:
        problems.append("action 为空")
    if not wo.scope:
        problems.append("scope 为空")
    if not wo.rules:
        problems.append("rules 为空")
    if not wo.prohibitions:
        problems.append("prohibitions 为空")
    if not wo.deliverable:
        problems.append("deliverable 为空")
    if not wo.deadline:
        problems.append("deadline 为空")
    return problems

