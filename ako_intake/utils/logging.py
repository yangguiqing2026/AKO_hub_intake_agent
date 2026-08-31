"""结构化日志（FI-II-08）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """JSON 结构化日志格式化器。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("session_id", "trace_id", "agent_id"):
            value = getattr(record, key, None)
            if value:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(log_dir: str | Path = "logs", level: str = "INFO") -> None:
    """初始化根日志器（结构化 JSON 输出到文件与控制台）。"""
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path / "intake.log", encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("ako_intake")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers = [handler]
    root.propagate = False


def get_logger(name: str, **extra: Any) -> logging.Logger:
    """获取带上下文字段的日志器（LoggerAdapter 附加字段）。"""
    logger = logging.getLogger(f"ako_intake.{name}")
    if extra:
        return logging.LoggerAdapter(logger, extra)  # type: ignore[return-value]
    return logger
