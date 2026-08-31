"""pytest 公共夹具。"""

from __future__ import annotations

import pytest

from ako_intake.config import AppConfig, IntakeSettings, TermEntry


@pytest.fixture
def config() -> AppConfig:
    """最小配置（临时路径）。"""
    cfg = AppConfig(
        intake=IntakeSettings(
            max_p0_rounds=3,
            question_timeout_seconds=300,
            max_questions_per_round=3,
            default_deadline_minutes=90,
            review_score_threshold=0.9,
            delivery_max_retries=3,
            retry_base_seconds=0,
            retry_max_seconds=0,
        ),
        terms=[
            TermEntry(term="报价", module="AKO_quote_agent", actions=["审计", "修复", "查看"]),
            TermEntry(term="图纸", module="AKO_drawing_inspector_agent", actions=["审查", "检查"]),
            TermEntry(term="排版", module="AKO_layout_agent", actions=["生成图册", "排版"]),
            TermEntry(term="设计", module="AKO_architect_agent", actions=["方案设计", "结构计算"]),
        ],
    )
    return cfg.resolve_paths()


@pytest.fixture
def sample_text() -> str:
    return "帮我看看报价模块最近的数据有没有问题"

