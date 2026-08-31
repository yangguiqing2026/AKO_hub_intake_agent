"""IntakeSpoke 协议兼容。"""

from __future__ import annotations

from ako_intake.adapters.spoke import IntakeSpoke


def test_spoke_run_resolved(config) -> None:
    spoke = IntakeSpoke(config)
    result = spoke.run(intent="修复报价模块的bug，只动校验逻辑，不动数据库")
    assert result["error"] is None
    assert "工单" in result["summary"]
    assert isinstance(result["output_files"], list)


def test_spoke_run_ambiguous_returns_questions(config) -> None:
    spoke = IntakeSpoke(config)
    result = spoke.run(intent="帮我看看报价模块的数据")
    assert result["error"] is None
    assert "澄清" in result["summary"]


def test_spoke_create_task(config) -> None:
    spoke = IntakeSpoke(config)
    task_id = spoke.create_task({"raw_text": "修复报价模块的bug，只动校验逻辑"})
    assert task_id.startswith("sess-")

