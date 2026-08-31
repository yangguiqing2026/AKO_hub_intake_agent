"""CLI 入口：serve / parse / status / queue。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from ako_intake.config import AppConfig, load_config
from ako_intake.db.queue_store import QueueStore
from ako_intake.db.session_store import SessionStore
from ako_intake.services.ambiguity_detector import detect_ambiguities
from ako_intake.services.nlu_parser import parse_intent


def cmd_parse(config: AppConfig, text: str) -> int:
    """单次解析 + 歧义检测。"""
    tree = parse_intent(text, config.terms)
    report = detect_ambiguities(tree)
    print(json.dumps({"intent_tree": tree.model_dump(), "ambiguity_report": report.model_dump()}, ensure_ascii=False, indent=2))
    return 0


def cmd_status(config: AppConfig, session_id: str) -> int:
    store = SessionStore(config.db.session_db)
    state = store.load(session_id)
    if state is None:
        print(json.dumps({"error": "session not found", "session_id": session_id}, ensure_ascii=False))
        return 1
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_queue(config: AppConfig) -> int:
    store = QueueStore(config.db.queue_db)
    print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
    return 0


def cmd_serve(config: AppConfig, host: str, port: int) -> int:
    """启动 FastAPI 服务。"""
    import uvicorn

    uvicorn.run("app:app", host=host, port=port, reload=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ako_intake", description="AKO_hub_intake_agent CLI")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="解析自然语言并检测歧义")
    p_parse.add_argument("--text", required=True, help="自然语言输入")

    p_status = sub.add_parser("status", help="查询会话状态")
    p_status.add_argument("--session", required=True, help="Session ID")

    sub.add_parser("queue", help="查看本地投递队列统计")

    p_serve = sub.add_parser("serve", help="启动 HTTP/WS 服务")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    return parser


def main(argv: List[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == "parse":
        return cmd_parse(config, args.text)
    if args.command == "status":
        return cmd_status(config, args.session)
    if args.command == "queue":
        return cmd_queue(config)
    if args.command == "serve":
        host = args.host or config.host
        port = args.port or config.port
        return cmd_serve(config, host, port)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
