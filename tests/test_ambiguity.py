"""M02 歧义检测：L1/L2 漏检率 = 0。"""

from __future__ import annotations

from ako_intake.services.ambiguity_detector import detect_ambiguities
from ako_intake.services.nlu_parser import parse_intent


def test_fatal_when_no_action(config) -> None:
    tree = parse_intent("报价模块的数据汇总", config.terms)
    report = detect_ambiguities(tree)
    assert report.fatal, "缺少动作必须触发 L1 致命歧义"


def test_core_when_action_ambiguous(config) -> None:
    tree = parse_intent("帮我看看报价模块的数据", config.terms)
    report = detect_ambiguities(tree)
    assert not report.fatal
    assert any(item.level == "L1" for item in report.core)
    assert any(item.level == "L2" for item in report.core), "范围未声明必须触发 L2"


def test_resolved_input_no_l1_l2(config) -> None:
    tree = parse_intent("修复报价模块的bug，只动校验逻辑，不动数据库", config.terms)
    report = detect_ambiguities(tree)
    assert not report.fatal
    assert not report.core
    assert not report.needs_clarification(), "已声明动作与范围不应强制 P0"


def test_l1_l2_miss_rate_zero(config) -> None:
    """构造含致命/核心歧义的用例，验证全部触发 P0。"""
    cases = [
        "报价模块最近的数据",
        "看看排版模块的模板",
        "设计图纸的方案，范围未定",
        "请处理一下图纸",
    ]
    for text in cases:
        report = detect_ambiguities(parse_intent(text, config.terms))
        assert report.needs_clarification(), f"漏检: {text}"

