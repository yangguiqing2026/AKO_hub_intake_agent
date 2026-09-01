"""配置加载测试（FI-II-07）。"""

from __future__ import annotations

from ako_intake.config import load_config


def test_default_port_is_5026() -> None:
    config = load_config()
    assert config.port == 5026


def test_ws_settings_loaded() -> None:
    config = load_config()
    assert config.ws.heartbeat_seconds >= 1
    assert config.ws.stream_ack_bytes >= 1024
    assert config.ws.auth_timeout_seconds >= 1


def test_ws_settings_explicit_values() -> None:
    """yaml 显式值断言（终审 FW-8）。"""
    config = load_config()
    assert config.ws.heartbeat_seconds == 30 and config.ws.stream_ack_bytes == 16384 and config.ws.auth_timeout_seconds == 10
