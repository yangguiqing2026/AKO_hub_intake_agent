"""结构化日志。"""

from __future__ import annotations

import json
from pathlib import Path

from ako_intake.utils.logging import JsonFormatter, get_logger, setup_logging


def test_setup_logging_writes_json(tmp_path) -> None:
    setup_logging(tmp_path / "logs")
    logger = get_logger("test", session_id="sess-x")
    logger.info("hello")
    lines = (tmp_path / "logs" / "intake.log").read_text(encoding="utf-8").strip().splitlines()
    assert lines
    record = json.loads(lines[0])
    assert record["message"] == "hello"
    assert record["session_id"] == "sess-x"


def test_json_formatter_includes_exc() -> None:
    formatter = JsonFormatter()
    import logging

    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, None)
    record.exc_info = (ValueError, ValueError("x"), None)
    payload = json.loads(formatter.format(record))
    assert "exc" in payload

