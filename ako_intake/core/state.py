"""IntakeState TypedDict（LangGraph 状态）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class IntakeState(TypedDict, total=False):
    """会话状态对象。"""

    session_id: str
    status: str
    raw_input: str
    intent_tree: Dict[str, Any]
    ambiguity_report: Dict[str, Any]
    clarification_log: List[Dict[str, Any]]
    pending_answers: List[Dict[str, Any]]
    pending_questions: List[Dict[str, Any]]
    p0_rounds: int
    draft_work_order: Dict[str, Any]
    review_record: Dict[str, Any]
    semantic_review_score: float
    human_confirmed: bool
    hub_ack: Dict[str, Any]
    queue: str
    error: Optional[str]
    created_at: str
    updated_at: str
