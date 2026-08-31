"""M07 Independent Reviewer：结构评审 + 语义评审（生成与评审分离）。"""

from __future__ import annotations

from typing import List, Optional

from ako_intake.models import Ako1WorkOrder, ReviewRecord
from ako_intake.services.form_builder import validate_work_order


def _structural_score(problems: List[str]) -> float:
    """结构得分：无问题 1.0，存在问题 0.6。"""
    return 1.0 if not problems else 0.6


def review_work_order(
    wo: Ako1WorkOrder,
    threshold: float = 0.9,
    semantic_score: Optional[float] = None,
) -> ReviewRecord:
    """执行独立评审。semantic_score 为 None 时由调用方注入（LLM 或回退值）。"""
    problems = validate_work_order(wo)
    structural = _structural_score(problems)
    semantic = semantic_score if semantic_score is not None else 1.0
    score = round(min(structural, semantic), 4)
    return ReviewRecord(
        review_score=score,
        structural_passed=not problems,
        differences=problems,
    )


def should_require_human(review_record: ReviewRecord, threshold: float) -> bool:
    """review_score < 阈值 → 强制人工确认。"""
    return review_record.review_score < threshold

