"""LangGraph 状态机：转换、断点续传、无死锁。"""

from __future__ import annotations

from ako_intake.core.graph import compile_graph


def _initial(session_id: str = "sess-t") -> dict:
    return {
        "session_id": session_id,
        "status": "PARSING",
        "raw_input": "修复报价模块的bug，只动校验逻辑，不动数据库",
        "clarification_log": [],
        "pending_answers": [],
        "p0_rounds": 0,
        "queue": "main",
    }


def test_resolved_flow_reaches_delivered(config) -> None:
    graph = compile_graph(config)
    result = graph.invoke(_initial())
    assert result["status"] == "DELIVERED"
    assert result["draft_work_order"]["module"] == "AKO_quote_agent"
    assert result["review_record"]["review_score"] >= 0.9


def test_ambiguous_flow_waits_for_user(config) -> None:
    graph = compile_graph(config)
    state = _initial("sess-a")
    state["raw_input"] = "帮我看看报价模块的数据"
    result = graph.invoke(state)
    assert result["status"] == "CLARIFYING"
    assert result["pending_questions"], "等待用户时应返回反问卡片"


def test_rounds_exhausted_goes_manual_review(config) -> None:
    graph = compile_graph(config)
    state = _initial("sess-m")
    state["raw_input"] = "帮我看看报价模块的数据"
    state["p0_rounds"] = 3  # 已达最大轮次
    result = graph.invoke(state)
    assert result["status"] == "MANUAL_REVIEW"
    assert result["queue"] == "manual_review"


def test_breakpoint_resume_preserves_clarification(config) -> None:
    """断点续传：已澄清动作/范围后重跑不再覆盖。"""
    graph = compile_graph(config)
    first = graph.invoke(_initial("sess-r"))
    assert first["status"] == "DELIVERED"
    resumed = graph.invoke(first)
    assert resumed["session_id"] == "sess-r"
    assert resumed["draft_work_order"]["action"] == first["draft_work_order"]["action"]


def test_low_review_score_routes_manual_review(config) -> None:
    graph = compile_graph(config)
    state = _initial("sess-l")
    state["semantic_review_score"] = 0.5
    result = graph.invoke(state)
    assert result["status"] == "MANUAL_REVIEW"


def test_human_confirm_overrides_low_score(config) -> None:
    graph = compile_graph(config)
    state = _initial("sess-h")
    state["semantic_review_score"] = 0.5
    state["human_confirmed"] = True
    result = graph.invoke(state)
    assert result["status"] == "DELIVERED"

