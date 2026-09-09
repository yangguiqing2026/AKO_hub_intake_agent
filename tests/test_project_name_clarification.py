"""2026-09-04：报价类任务项目名称澄清——报价单抬头与用户输入必须一致。

覆盖链路：quote 域动作收敛且无项目名 → detect 产生 project_name 追问 →
答复写入意图树 entities → build_work_order 携带 project_name。
非报价动作（如"修复报价模块"）不得触发该追问（术语表路由不误伤）。
"""

from __future__ import annotations

from ako_intake.models import Answer, AmbiguityReport, Entity, IntentTree
from ako_intake.services.ambiguity_detector import detect_ambiguities
from ako_intake.services.form_builder import build_work_order
from ako_intake.services.interrogator import apply_answers, build_questions


def _quote_tree(project_name: str = "") -> IntentTree:
    entities = [
        Entity(type="module", value="AKO_quote_agent", confidence=0.92),
        Entity(type="scope", value="只做外墙报价，不动其他", confidence=1.0),
    ]
    if project_name:
        entities.append(Entity(type="project_name", value=project_name, confidence=1.0))
    return IntentTree(entities=entities, action_candidates=["报价"])


def test_quote_domain_without_project_name_needs_clarification() -> None:
    report = detect_ambiguities(_quote_tree())
    fields = [item.field for item in report.fatal + report.core]
    assert "project_name" in fields, "报价任务未给项目名必须追问"
    item = next(i for i in report.fatal + report.core if i.field == "project_name")
    assert item.required_clarification is True


def test_quote_domain_with_project_name_skips_question() -> None:
    report = detect_ambiguities(_quote_tree(project_name="桐木岭城市微更新商业体"))
    fields = [item.field for item in report.fatal + report.core]
    assert "project_name" not in fields, "已给出项目名不应再追问"


def test_non_quote_action_no_project_question() -> None:
    """修复报价模块的 bug 是修复任务，术语表路由到 quote 也不得追问项目名。"""
    tree = IntentTree(
        entities=[
            Entity(type="module", value="AKO_quote_agent", confidence=0.92),
            Entity(type="scope", value="只动校验逻辑，不动数据库", confidence=1.0),
        ],
        action_candidates=["修复"],
    )
    report = detect_ambiguities(tree)
    fields = [item.field for item in report.fatal + report.core]
    assert "project_name" not in fields


def test_project_name_question_is_open_required() -> None:
    report = AmbiguityReport()
    report.core.append(_fake_ambiguity("project_name"))
    questions = build_questions(report, round_no=3)
    assert len(questions) == 1
    q = questions[0]
    assert q.field == "project_name"
    assert q.qid == "q-3-project_name"
    assert q.required is True


def test_project_name_answer_written_back() -> None:
    tree = apply_answers(_quote_tree(), [Answer(qid="q-3-project_name", value=" 桐木岭城市微更新商业体 ")])
    assert tree.entity_value("project_name") == "桐木岭城市微更新商业体"


def test_project_name_answer_strips_lead_prefix() -> None:
    """2026-09-09：用户复述问句（“测试项目名称是测试项目A”）只取项目名本体，
    否则报价单抬头带脏句。"""
    for raw, expected in [
        ("测试项目名称是测试项目A", "测试项目A"),
        ("项目叫桃花源改造", "桃花源改造"),
        ("这个项目名称：桐木岭微更新", "桐木岭微更新"),
        ("桐木岭城市微更新商业体", "桐木岭城市微更新商业体"),  # 无前缀原样
        ("项目是桃花源", "桃花源"),
    ]:
        tree = apply_answers(_quote_tree(), [Answer(qid="q-3-project_name", value=raw)])
        assert tree.entity_value("project_name") == expected, f"输入 {raw!r}"


def test_build_work_order_carries_project_name(config) -> None:
    from ako_intake.core.state import IntakeState  # noqa: F401  # 仅触发包导入路径

    tree = apply_answers(_quote_tree(), [Answer(qid="q-2-project_name", value="桐木岭城市微更新商业体")])
    wo = build_work_order(tree, [], config.intake, session_id="sess-t")
    assert wo.project_name == "桐木岭城市微更新商业体"
    assert "project_name" in wo.to_payload()


def _fake_ambiguity(field: str):
    from ako_intake.models import AmbiguityItem

    return AmbiguityItem(field=field, issue="test", level="L2", confidence=0.6, required_clarification=True)
