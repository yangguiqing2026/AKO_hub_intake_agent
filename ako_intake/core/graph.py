"""LangGraph 状态机（S00-S95，白皮书 v1.1.0 第八章）。"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from ako_intake.config import AppConfig
from ako_intake.core.state import IntakeState
from ako_intake.models import (
    AmbiguityReport,
    ClarificationLogEntry,
    IntentTree,
    Question,
    ReviewRecord,
)
from ako_intake.services.ambiguity_detector import detect_ambiguities
from ako_intake.services.form_builder import build_work_order, validate_work_order
from ako_intake.services.interrogator import apply_answers, build_log_entry, build_questions, still_unresolved, module_action_options
from ako_intake.services.nlu_parser import parse_intent
from ako_intake.services.reviewer import review_work_order, should_require_human


def _now() -> str:
    from datetime import datetime

    return datetime.now().isoformat()


def build_nodes(config: AppConfig) -> Dict[str, object]:
    """构造状态机节点闭包。"""
    threshold = config.intake.review_score_threshold
    max_rounds = config.intake.max_p0_rounds
    max_questions = config.intake.max_questions_per_round

    def parse_node(state: IntakeState) -> Dict[str, Any]:
        # 幂等：已澄清动作/范围的会话不重复解析，保留人工确认结果
        if state.get("intent_tree"):
            tree = IntentTree.model_validate(state["intent_tree"])
            if tree.entity_value("action") and tree.entity_value("scope"):
                return {"updated_at": _now()}
        tree = parse_intent(state.get("raw_input", ""), config.terms)
        return {
            "intent_tree": tree.model_dump(),
            "status": "AMBIGUITY_DETECTED",
            "updated_at": _now(),
        }

    def detect_node(state: IntakeState) -> Dict[str, Any]:
        tree = IntentTree.model_validate(state["intent_tree"])
        report = detect_ambiguities(tree)
        return {"ambiguity_report": report.model_dump(), "status": "AMBIGUITY_DETECTED"}

    def interrogate_node(state: IntakeState) -> Dict[str, Any]:
        report = AmbiguityReport.model_validate(state["ambiguity_report"])
        answers = state.get("pending_answers", [])
        tree = IntentTree.model_validate(state["intent_tree"])
        log = list(state.get("clarification_log", []))
        pending = state.get("pending_questions") or []

        # 2026-09-03 修复①：澄清态收到无答复重入（用户把答复当新文本发送等）
        # 不烧轮次——原样重发问题，等待结构化答复。
        if not answers and pending:
            return {
                "pending_questions": pending,
                "status": "CLARIFYING",
            }

        round_no = int(state.get("p0_rounds", 0)) + 1
        if answers:
            tree = apply_answers(tree, answers)
            entry = build_log_entry(round_no, [], answers)
            log.append(entry.model_dump())
            report = detect_ambiguities(tree)
        questions = build_questions(report, round_no, max_questions)
        # 2026-09-03 修复②：action 选项按目标 module 补全业务动词（quote→报价/预算…）
        module_value = tree.entity_value("module") or ""
        questions = [
            q.model_copy(update={"options": module_action_options(module_value)})
            if q.field == "action"
            else q
            for q in questions
        ]
        return {
            "intent_tree": tree.model_dump(),
            "ambiguity_report": report.model_dump(),
            "clarification_log": log,
            "pending_questions": [q.model_dump() for q in questions],
            "pending_answers": [],
            "p0_rounds": round_no,
            "status": "CLARIFYING",
        }

    def build_node(state: IntakeState) -> Dict[str, Any]:
        tree = IntentTree.model_validate(state["intent_tree"])
        log = [ClarificationLogEntry.model_validate(item) for item in state.get("clarification_log", [])]
        seq = int(state.get("p0_rounds", 0)) + 1
        wo = build_work_order(tree, log, config.intake, state.get("session_id", "sess"), seq=seq)
        return {"draft_work_order": wo.model_dump(), "status": "FORM_BUILDING"}

    def validate_node(state: IntakeState) -> Dict[str, Any]:
        from ako_intake.models import Ako1WorkOrder

        wo = Ako1WorkOrder.model_validate(state["draft_work_order"])
        problems = validate_work_order(wo)
        if problems:
            return {"status": "FAILED", "error": "schema_error: " + "; ".join(problems)}
        return {"status": "VALIDATING"}

    def review_node(state: IntakeState) -> Dict[str, Any]:
        from ako_intake.models import Ako1WorkOrder

        wo = Ako1WorkOrder.model_validate(state["draft_work_order"])
        semantic = state.get("semantic_review_score")
        record = review_work_order(wo, threshold, semantic_score=semantic)
        return {"review_record": record.model_dump(), "status": "REVIEWING"}

    def deliver_node(state: IntakeState) -> Dict[str, Any]:
        return {"status": "DELIVERED", "hub_ack": state.get("hub_ack", {})}

    def manual_review_node(state: IntakeState) -> Dict[str, Any]:
        # 2026-09-03 修复③：转人工时落真实理由，区分两类入队——
        # a) 独立评审（M07）低于阈值待人工确认；b) P0 消歧超轮未收敛
        if state.get("review_record"):
            reason = "独立评审（M07）低于阈值，草稿待人工确认后继续投递"
        else:
            rounds = int(state.get("p0_rounds", 0))
            fields: List[str] = []
            try:
                rep = state.get("ambiguity_report") or {}
                for grp in ("fatal", "core"):
                    fields.extend(str(f.get("field", "")) for f in rep.get(grp, []))
            except Exception:
                pass
            detail = "/".join(dict.fromkeys(f for f in fields if f)) or "多歧义未收敛"
            reason = f"P0 消歧 {rounds} 轮未收敛，转人工审核（未决: {detail}）"
        return {"status": "MANUAL_REVIEW", "queue": "manual_review", "error": reason}

    def fail_node(state: IntakeState) -> Dict[str, Any]:
        return {"status": "FAILED", "error": state.get("error", "unknown")}

    def route_after_detect(state: IntakeState) -> str:
        report = AmbiguityReport.model_validate(state["ambiguity_report"])
        return "interrogate" if report.needs_clarification() else "build"

    def route_after_interrogate(state: IntakeState) -> str:
        report = AmbiguityReport.model_validate(state["ambiguity_report"])
        rounds = int(state.get("p0_rounds", 0))
        if report.resolved():
            return "build"
        if rounds >= max_rounds:
            return "manual_review"
        return END  # 等待用户下一轮答复

    def route_after_validate(state: IntakeState) -> str:
        return "review" if state.get("status") == "VALIDATING" else "fail"

    def route_after_review(state: IntakeState) -> str:
        record = ReviewRecord.model_validate(state["review_record"])
        if should_require_human(record, threshold) and not state.get("human_confirmed"):
            return "manual_review"
        return "deliver"

    return {
        "parse": parse_node,
        "detect": detect_node,
        "interrogate": interrogate_node,
        "build": build_node,
        "validate": validate_node,
        "review": review_node,
        "deliver": deliver_node,
        "manual_review": manual_review_node,
        "fail": fail_node,
        "route_after_detect": route_after_detect,
        "route_after_interrogate": route_after_interrogate,
        "route_after_validate": route_after_validate,
        "route_after_review": route_after_review,
    }


def compile_graph(config: AppConfig):
    """编译 LangGraph 状态机。"""
    nodes = build_nodes(config)
    builder = StateGraph(IntakeState)
    builder.add_node("parse", nodes["parse"])
    builder.add_node("detect", nodes["detect"])
    builder.add_node("interrogate", nodes["interrogate"])
    builder.add_node("build", nodes["build"])
    builder.add_node("validate", nodes["validate"])
    builder.add_node("review", nodes["review"])
    builder.add_node("deliver", nodes["deliver"])
    builder.add_node("manual_review", nodes["manual_review"])
    builder.add_node("fail", nodes["fail"])

    builder.add_edge(START, "parse")
    builder.add_edge("parse", "detect")
    builder.add_conditional_edges("detect", nodes["route_after_detect"], {"interrogate": "interrogate", "build": "build"})
    builder.add_conditional_edges(
        "interrogate",
        nodes["route_after_interrogate"],
        {"build": "build", "manual_review": "manual_review", END: END},
    )
    builder.add_edge("build", "validate")
    builder.add_conditional_edges("validate", nodes["route_after_validate"], {"review": "review", "fail": "fail"})
    builder.add_conditional_edges(
        "review",
        nodes["route_after_review"],
        {"deliver": "deliver", "manual_review": "manual_review"},
    )
    builder.add_edge("deliver", END)
    builder.add_edge("manual_review", END)
    builder.add_edge("fail", END)
    return builder.compile()
