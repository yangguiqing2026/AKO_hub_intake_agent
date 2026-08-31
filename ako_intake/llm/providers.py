"""LLM 提供方客户端（ollama / deepseek，网络失败时抛错）。"""

from __future__ import annotations

from typing import Any, Dict

import httpx


def chat_completion(
    prompt: str,
    model: str,
    base_url: str,
    api_key: str = "",
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """调用 OpenAI 兼容 /chat/completions 端点。"""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    return {"content": data["choices"][0]["message"]["content"]}

