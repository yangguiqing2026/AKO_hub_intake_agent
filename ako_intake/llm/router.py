"""模型分级路由（简单→规则/小模型，复杂→大模型）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteDecision:
    """路由决策。"""

    model: str
    tier: str
    estimated_cost_tokens: int


def classify_complexity(text: str, length_threshold: int = 80) -> str:
    """按输入长度与特征粗略分级。"""
    if len(text) > length_threshold or any(k in text for k in ("且", "并且", "但是", "如果", "分别")):
        return "complex"
    return "simple"


def route_task(text: str, simple_model: str, complex_model: str) -> RouteDecision:
    """返回模型路由决策。"""
    tier = classify_complexity(text)
    model = complex_model if tier == "complex" else simple_model
    return RouteDecision(model=model, tier=tier, estimated_cost_tokens=len(text))

