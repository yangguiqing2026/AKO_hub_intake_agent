"""registry 门禁：等级 + 信任边界（VETO-09）。"""

from __future__ import annotations

from ako_intake.gateways.registry_client import evaluate_manifest, verify_target


def _manifest(level: str = "S") -> dict:
    return {
        "level": level,
        "capabilities": [{"id": "cap_x"}],
        "allowed_callers": ["AKO_hub_agent"],
        "data_access_level": "INTERNAL",
        "consistency_requirement": "read_your_writes",
        "resource_quota": {"max_tokens_per_call": 4000},
    }


def test_s_level_deployable() -> None:
    result = evaluate_manifest(_manifest("S"))
    assert result.registered and result.deployable and result.trust_boundary_ok


def test_c_level_not_deployable() -> None:
    result = evaluate_manifest(_manifest("C"))
    assert not result.deployable


def test_unrated_not_deployable() -> None:
    result = evaluate_manifest({})
    assert not result.registered
    assert not result.deployable


def test_missing_trust_boundary_triggers_veto() -> None:
    result = evaluate_manifest({"level": "A", "capabilities": []})
    assert not result.trust_boundary_ok
    assert "allowed_callers 为空" in result.reasons


def test_verify_target_mock_uses_local_manifest() -> None:
    result = verify_target("AKO_quote_agent", "AKO_hub_intake_agent", base_url="", local_manifest=_manifest("A"))
    assert result.deployable and result.level == "A"

