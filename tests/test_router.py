"""模型分级路由（FI-IV-04）。"""

from __future__ import annotations

from ako_intake.llm.router import classify_complexity, route_task


def test_classify_complexity() -> None:
    assert classify_complexity("查报价") == "simple"
    assert classify_complexity("如果报价异常并且范围较大，分别处理") == "complex"


def test_route_task_models() -> None:
    simple = route_task("查报价", "qwen2.5-7b", "deepseek-v3")
    assert simple.model == "qwen2.5-7b"
    complex_ = route_task("如果报价异常并且范围较大，分别处理", "qwen2.5-7b", "deepseek-v3")
    assert complex_.model == "deepseek-v3"

