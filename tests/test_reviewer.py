"""M07 独立评审门控。"""

from __future__ import annotations

from ako_intake.config import IntakeSettings
from ako_intake.models import Ako1WorkOrder
from ako_intake.services.reviewer import review_work_order, should_require_human


def _valid_wo() -> Ako1WorkOrder:
    return Ako1WorkOrder(
        wo_number="WO-DRAFT-20260831-001",
        module="AKO_quote_agent",
        action="审计",
        scope="只动校验逻辑",
        rules=["不修改生产环境"],
        prohibitions=["禁止直接修改生产数据库"],
        deliverable="输出审计报告",
        deadline="90分钟",
    )


def test_structural_failure_lowers_score() -> None:
    wo = _valid_wo().model_copy(update={"scope": ""})
    record = review_work_order(wo, threshold=0.9)
    assert record.review_score < 0.9
    assert not record.structural_passed


def test_semantic_score_gates_human(config) -> None:
    wo = _valid_wo()
    low = review_work_order(wo, threshold=0.9, semantic_score=0.6)
    assert should_require_human(low, 0.9)
    high = review_work_order(wo, threshold=0.9, semantic_score=1.0)
    assert not should_require_human(high, 0.9)

