"""Hub 自启引导（2026-09-09）：intake 启动时确保 hub HTTP 层在位。

幂等：端口已监听即跳过；未监听则清理陈旧 hub 进程并拉起，轮询至多
HUB_START_TIMEOUT_S 秒。供 autostart_backend / run 入口调用，对齐
D:\\AKO\\AKO_hub\\AKO_hub_start.ps1 的语义（仅 hub 本体，不拉 :80 dashboard）。
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

from ako_intake.config import AppConfig

logger = logging.getLogger("ako_intake.hub_bootstrap")

HUB_DIR = Path(r"D:\AKO\AKO_hub")
HUB_START_TIMEOUT_S = 30.0
HUB_POLL_INTERVAL_S = 1.0


def parse_hub_addr(base_url: str) -> Tuple[str, int]:
    """从 hub_base_url 提取 (host, port)，默认 localhost:8080。"""
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080
    return host, port


def is_port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    """TCP 连通探测：端口已监听即视为服务在位。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def kill_stale_hub_processes() -> None:
    """清理陈旧 hub app.py 进程（对齐 AKO_hub_start.ps1，排除 intake 自身）。

    注意：CommandLine 不含工作目录，仅能按脚本名过滤；排除 'intake'
    防止误杀 autostart_backend（其命令行含 'AKO_hub_intake_agent' 前缀）。
    """
    ps = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') "
        "-and $_.CommandLine -match 'app\\.py' "
        "-and $_.CommandLine -notmatch 'intake' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("hub 陈旧进程清理失败，继续尝试拉起", exc_info=True)


def launch_hub() -> None:
    """拉起 hub app.py（:8080 HTTP + :5000 心跳），日志追加到 hub\\logs。

    脚本路径必须传**绝对路径**：进程 CommandLine 不含工作目录，而 AKO_hub 侧
    `_is_live_hub()` 依据命令行含 "AKO_hub" 判定实例存活 —— 传相对 "app.py"
    会让本进程对单实例锁不可见，触发双 hub（详见 2026-09-14 事故）。
    """
    log_dir = HUB_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = HUB_DIR / "app.py"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0)
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    with open(log_dir / "hub_out.log", "a", encoding="utf-8") as out, open(
        log_dir / "hub_err.log", "a", encoding="utf-8"
    ) as err:
        subprocess.Popen(
            [str(pythonw), str(script)],
            cwd=str(HUB_DIR),
            stdout=out,
            stderr=err,
            creationflags=flags,
        )
    logger.info("hub 已拉起（%s，:8080/:5000）", script)


def ensure_hub(config: AppConfig) -> bool:
    """确保 hub HTTP 层在位，返回是否就绪。幂等，可重复调用。"""
    host, port = parse_hub_addr(config.gateways.hub_base_url)
    if is_port_listening(host, port):
        return True
    kill_stale_hub_processes()
    launch_hub()
    deadline = time.monotonic() + HUB_START_TIMEOUT_S
    while time.monotonic() < deadline:
        if is_port_listening(host, port):
            return True
        time.sleep(HUB_POLL_INTERVAL_S)
    logger.error("hub 启动超时（%s:%d 未监听）", host, port)
    return False
