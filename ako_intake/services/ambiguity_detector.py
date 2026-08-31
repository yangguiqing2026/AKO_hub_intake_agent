"""M02 Ambiguity Detector：L1/L2/L3 歧义分级。"""

from __future__ import annotations

from typing import List

from ako_intake.models import AmbiguityItem, AmbiguityReport, IntentTree


def detect_ambiguities(intent_tree: IntentTree, threshold: float = 0.7) -> AmbiguityReport:
    """对照 ako1 八字段识别未声明变量并分级。"""
    report = AmbiguityReport()
    actions = intent_tree.action_candidates
    scope = intent_tree.entity_value("scope")

    if not actions:
        report.fatal.append(
            AmbiguityItem(
                field="action",
                issue="动作未识别：无法确定 修复/新增/重构/设计/审签",
                level="L1",
                confidence=0.0,
                required_clarification=True,
            )
        )
    elif len(actions) > 1:
        report.core.append(
            AmbiguityItem(
                field="action",
                issue=f"动作未明确：候选集 {actions}",
                level="L1",
                confidence=0.5,
                required_clarification=True,
            )
        )

    if not scope:
        report.core.append(
            AmbiguityItem(
                field="scope",
                issue="范围未声明：只动/不动 未指定",
                level="L2",
                confidence=0.45,
                required_clarification=True,
            )
        )

    report.minor = [
        AmbiguityItem(field="rules", issue="铁律未声明，可推断默认值", level="L3", confidence=0.75),
        AmbiguityItem(field="deliverable", issue="交付物未声明，可按动作推断", level="L3", confidence=0.8),
        AmbiguityItem(field="deadline", issue="时限未声明，可推断默认值", level="L3", confidence=0.85),
    ]
    return report


def first_questions(report: AmbiguityReport, limit: int = 3) -> List[AmbiguityItem]:
    """按 L1→L2→L3 优先级取待澄清条目。"""
    ordered = report.fatal + report.core + report.minor
    return ordered[:limit]

