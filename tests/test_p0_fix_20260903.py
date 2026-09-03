# -*- coding: utf-8 -*-
"""2026-09-03 P0_MAX_ROUNDS_EXCEEDED 回归测试。

背景：quote 域请求（"外墙板的报价"）因 action 词表不含业务动词 + 澄清态
无答复重入烧轮次 → 3 轮未收敛误转人工，前端显示误导性 P0_MAX_ROUNDS_EXCEEDED。
修复：module 化 action 选项/同义词归一/无答复不烧轮/manual 落真实理由/前端如实文案。
"""
from ako_intake.services.interrogator import (
    BASE_ACTION_OPTIONS,
    module_action_options,
    normalize_action_value,
)


def test_quote_module_action_options_include_baojia():
    opts = module_action_options("AKO_quote_agent")
    assert "报价" in opts
    assert "预算" in opts
    # 基础集保留且去重
    assert opts[0] == "报价"
    assert len(opts) == len(set(opts))
    for base in BASE_ACTION_OPTIONS:
        assert base in opts


def test_generic_module_keeps_base_options():
    opts = module_action_options("")
    assert opts == list(dict.fromkeys(BASE_ACTION_OPTIONS))
    assert "报价" not in opts


def test_normalize_action_synonyms():
    assert normalize_action_value("帮我报个价") == "报价"
    assert normalize_action_value("报价") == "报价"
    assert normalize_action_value("出报价单") == "报价"
    assert normalize_action_value("做个预算") == "预算"
    assert normalize_action_value("设计个方案") == "设计个方案"  # 无同义词时保留原样


def test_manual_review_node_carries_reason():
    """转人工时必须携带真实理由（轮次+未决字段），不再裸转。"""
    from ako_intake.config import load_config

    try:
        config = load_config()
    except Exception:
        import pytest

        pytest.skip("配置加载不可用")
    from ako_intake.core.graph import build_nodes

    nodes = build_nodes(config)
    state = {
        "p0_rounds": 3,
        "ambiguity_report": {
            "fatal": [{"field": "action", "issue": "x", "level": "L1", "confidence": 0.0, "required_clarification": True}],
            "core": [{"field": "scope", "issue": "y", "level": "L2", "confidence": 0.4, "required_clarification": True}],
            "minor": [],
        },
    }
    out = nodes["manual_review"](state)
    assert out["status"] == "MANUAL_REVIEW"
    assert out["queue"] == "manual_review"
    assert "3 轮" in out["error"] and "action" in out["error"]


def test_interrogate_no_answer_does_not_burn_round():
    """澄清态收到无答复重入：轮次不变、问题原样重发（防空转烧轮）。"""
    from ako_intake.config import load_config

    try:
        config = load_config()
    except Exception:
        import pytest

        pytest.skip("配置加载不可用")
    from ako_intake.core.graph import build_nodes

    nodes = build_nodes(config)
    state = {
        "p0_rounds": 2,
        "pending_questions": [{"qid": "q-2-action", "field": "action"}],
        "pending_answers": [],
        "intent_tree": {"entities": [], "action_candidates": [], "ambiguity_report": {"fatal": [], "core": [], "minor": []}},
        "ambiguity_report": {"fatal": [{"field": "action", "issue": "x", "level": "L1", "confidence": 0.0, "required_clarification": True}], "core": [], "minor": []},
        "clarification_log": [],
    }
    out = nodes["interrogate"](state)
    assert out["status"] == "CLARIFYING"
    assert out["pending_questions"] == state["pending_questions"]
    assert "p0_rounds" not in out or out.get("p0_rounds", 2) == 2


def test_multiround_progress_not_reset_by_reparse():
    """根因回归：跨轮消解进度不被重解析覆盖（parse_node 幂等守卫）。

    用户先答 action=报价、再答 scope → 应直抵投递，而非 action 被重解析清空
    导致 3 轮超限转人工（2026-09-03 P0_MAX/P0消歧超轮 事故根因）。
    """
    from ako_intake.config import load_config
    from ako_intake.core.graph import compile_graph
    from ako_intake.models import Answer

    cfg = load_config()
    g = compile_graph(cfg)
    raw = "给我一份300平米两层现代风格的住宅陶粒墙板的报价"

    def new_state():
        return {"session_id": "probe-t", "status": "PARSING", "raw_input": raw,
                "clarification_log": [], "pending_answers": [], "p0_rounds": 0, "queue": "main"}

    s = g.invoke(new_state())
    assert s.get("status") == "CLARIFYING"
    s["pending_answers"] = [Answer(qid="q-1-action", value="报价")]
    s2 = g.invoke(s)
    assert s2.get("intent_tree", {}).get("action_candidates") == ["报价"]
    assert not (s2.get("ambiguity_report") or {}).get("fatal")
    scope_qid = next(q["qid"] for q in s2.get("pending_questions", []) if q["field"] == "scope")
    s2["pending_answers"] = [Answer(qid=scope_qid, value="只做外墙板报价，不动结构")]
    s3 = g.invoke(s2)
    assert s3.get("status") == "DELIVERED", f"status={s3.get('status')}"
    assert s3.get("draft_work_order"), "应生成草稿工单"
