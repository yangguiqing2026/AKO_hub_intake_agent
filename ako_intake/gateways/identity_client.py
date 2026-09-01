"""身份门禁客户端（AKO_identity_service :5025）。"""

from __future__ import annotations

from typing import Any, Dict

import httpx


def verify_human(token: str, base_url: str = "", timeout: float = 10.0) -> Dict[str, Any]:
    """校验人类身份。

    base_url 为空时返回 mock 结果（本地/测试模式）；否则调用 identity 服务 /verify。
    """
    if not base_url:
        return {"ok": True, "human_id": "mock-human", "method": "mock"}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url.rstrip('/')}/verify", json={"token": token})
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "method": "http"}


def login_human(account: str, fingerprint: str, base_url: str = "", timeout: float = 10.0) -> Dict[str, Any]:
    """人类登录（A.5 第一重）。

    base_url 为空时返回开发态令牌（仅非生产，设计 R3）。
    """
    if not base_url:
        return {"ok": True, "token": "dev-token", "human_id": "mock-human", "method": "mock"}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/login",
                json={"account": account, "fingerprint": fingerprint},
            )
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "method": "http"}

