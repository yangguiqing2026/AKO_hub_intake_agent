"""M01 NLU Parser：自然语言 → 意图树（规则优先，LLM 增强可选）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from ako_intake.config import TermEntry
from ako_intake.models import Entity, IntentTree

ACTION_KEYWORDS: dict[str, List[str]] = {
    "审计": ["审计"],
    "修复": ["修复"],
    "优化": ["优化"],
    "设计": ["方案设计", "结构计算"],
    "审查": ["审查"],
    "生成": ["生成"],
    "排版": ["排版"],
    "看看": ["审计", "修复", "查看"],
    "检查": ["审查", "检查"],
}

SCOPE_PATTERN_ATTRS = ("只动", "仅动", "不要动", "不动", "不动数据库")


def _find_module(raw_text: str, terms: List[TermEntry]) -> Optional[Entity]:
    """按术语表匹配模块实体。"""
    for entry in terms:
        if entry.term and entry.term in raw_text:
            return Entity(type="module", value=entry.module, confidence=0.92)
    return None


def _find_actions(raw_text: str) -> List[str]:
    """匹配动作候选集。"""
    candidates: List[str] = []
    for keyword, actions in ACTION_KEYWORDS.items():
        if keyword in raw_text:
            candidates.extend(actions)
    return candidates


def _find_scope(raw_text: str) -> Optional[str]:
    """抽取范围声明（只动/不动句式）。"""
    if "只动" in raw_text or "仅动" in raw_text:
        start = raw_text.find("只动") if "只动" in raw_text else raw_text.find("仅动")
        return raw_text[start : start + 40].split("，")[0]
    if "不动" in raw_text:
        return "只审计，不动任何代码/数据"
    return None


def _find_time_ref(raw_text: str) -> Optional[Entity]:
    """解析时间指代（最近/N天）。"""
    if "最近" in raw_text:
        end = datetime.now()
        start = end - timedelta(days=7)
        return Entity(
            type="time_ref",
            value="最近",
            confidence=0.9,
        )
    return None


def parse_intent(raw_text: str, terms: List[TermEntry] | None = None) -> IntentTree:
    """规则版语义解析：返回意图树。"""
    terms = terms or []
    entities: List[Entity] = []
    module = _find_module(raw_text, terms)
    if module:
        entities.append(module)
    scope = _find_scope(raw_text)
    if scope:
        entities.append(Entity(type="scope", value=scope, confidence=0.8))
    time_ref = _find_time_ref(raw_text)
    if time_ref:
        entities.append(time_ref)
    actions = _find_actions(raw_text)
    return IntentTree(entities=entities, action_candidates=actions)


def parse_with_model(raw_text: str, chat_fn: object) -> IntentTree:
    """LLM 增强路径（prompt 工程约束解析范围）。"""
    prompt = (
        "你是 AKO 工单解析器。从下面用户输入中提取 entities（module/action/scope/time_ref）"
        "与 action_candidates，仅输出 JSON。\n输入：" + raw_text
    )
    content = chat_fn(prompt)  # type: ignore[operator]
    import json

    data = json.loads(content)
    return IntentTree.model_validate(data)

