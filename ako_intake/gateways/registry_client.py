"""registry 门禁客户端（等级 + 信任边界校验，VETO-09）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ako_intake.models import RegistryVerifyResult

DEPLOYABLE_LEVELS = ("S", "A", "B")
TRUST_FIELDS = ("capabilities", "allowed_callers", "data_access_level", "consistency_requirement", "resource_quota")


def evaluate_manifest(manifest: Optional[Dict[str, Any]]) -> RegistryVerifyResult:
    """本地评估注册清单（无网络时的等价校验）。"""
    if not manifest:
        return RegistryVerifyResult(reasons=["未注册"])
    level = str(manifest.get("level", "unrated"))
    capabilities = manifest.get("capabilities") or manifest.get("trust_boundary", {}).get("capabilities")
    allowed_callers = manifest.get("allowed_callers") or (manifest.get("trust_boundary") or {}).get("allowed_callers")
    data_access_level = manifest.get("data_access_level") or (manifest.get("trust_boundary") or {}).get("data_access_level")
    consistency = manifest.get("consistency_requirement") or (manifest.get("trust_boundary") or {}).get("consistency_requirement")
    quota = manifest.get("resource_quota") or (manifest.get("trust_boundary") or {}).get("resource_quota")
    trust_boundary_ok = bool(
        capabilities and allowed_callers and data_access_level and consistency and quota
    )
    reasons: list[str] = []
    if not capabilities:
        reasons.append("capabilities 缺失")
    if not allowed_callers:
        reasons.append("allowed_callers 为空")
    if not data_access_level:
        reasons.append("data_access_level 缺失")
    if not consistency:
        reasons.append("consistency_requirement 缺失")
    if not quota:
        reasons.append("resource_quota 缺失")
    return RegistryVerifyResult(
        registered=True,
        level=level,
        deployable=level in DEPLOYABLE_LEVELS,
        trust_boundary_ok=trust_boundary_ok,
        reasons=reasons,
    )


def verify_target(
    agent_id: str,
    caller: str,
    base_url: str = "",
    local_manifest: Optional[Dict[str, Any]] = None,
    api_prefix: str = "/ako/api/v1/registry",
    timeout: float = 10.0,
) -> RegistryVerifyResult:
    """投递前校验目标 agent 等级与信任边界。"""
    if not base_url:
        return evaluate_manifest(local_manifest)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}{api_prefix}/verify",
                json={"agent_id": agent_id, "caller": caller},
            )
            response.raise_for_status()
            return RegistryVerifyResult.model_validate(response.json())
    except Exception as exc:
        return RegistryVerifyResult(reasons=[f"verify 调用失败: {exc}"])

