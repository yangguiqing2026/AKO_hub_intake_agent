"""M02 Ambiguity Detector：L1/L2/L3 歧义分级。"""

from __future__ import annotations

import re
from typing import List

from ako_intake.models import AmbiguityItem, AmbiguityReport, IntentTree

# 非交付类动作：路由到 quote 模块但不是"出报价"，不应追问项目名。
# 排除"修复报价模块的 bug"这类任务——术语表里的"报价"一词会把它们一并
# 路由到 AKO_quote_agent，但它们不产出报价单，没有抬头可言。
_NON_DELIVERY_ACTION = re.compile(r"修复|修改|排查|排障|调试|定位|检查|审计|重构|回滚|删除|优化")


def domain_is_quote(intent_tree: IntentTree) -> bool:
    """报价域判定：需要报价单抬头（项目名）的交付类任务。

    两条判定路径，满足其一即可：

    1. 动作已收敛为报价/预算类行为（原判定）；
    2. **2026-09-14 放宽**：module 路由到 AKO_quote_agent，且动作不是
       修复/排障类。

    第 2 条的由来——实测单号 F-AKO_akodoc_20260909_100807：输入
    「生成一个345平米的3层住宅的陶粒墙板报价书」动作收敛为「生成」，
    原判定只认报价动作 → 项目名门禁未触发 → project_name 留空 →
    报价单抬头落域默认值 taoli。口语化的「帮我出一份外墙报价单」更极端，
    动作完全不收敛（action_candidates 为空），同样漏判。

    修复/排障动作必须排除（`_NON_DELIVERY_ACTION`），否则
    「修复报价模块的 bug，只动校验逻辑」会被追问项目名——原判定正是
    为避免这一点才只认动作收敛值。
    """
    for action in intent_tree.action_candidates:
        if action in ("报价", "预算") or "报价" in action or "预算" in action:
            return True
    module = intent_tree.entity_value("module") or ""
    if "quote" not in module.lower():
        return False
    return not _NON_DELIVERY_ACTION.search(" ".join(intent_tree.action_candidates))


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

    # 2026-09-04：报价类任务项目名称必须澄清——报价单抬头项目名与用户输入须一致，
    # 不得让下游以域默认值（taoli）落单。
    if domain_is_quote(intent_tree) and not intent_tree.entity_value("project_name"):
        report.core.append(
            AmbiguityItem(
                field="project_name",
                issue="报价项目名称未声明：报价单抬头需用户指定项目名",
                level="L2",
                confidence=0.6,
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

