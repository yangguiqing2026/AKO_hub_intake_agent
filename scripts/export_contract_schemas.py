"""从 Pydantic 模型导出契约 JSON Schema 到 schemas/（设计 7.2 单一事实源）。"""

from __future__ import annotations

import json
from pathlib import Path

from ako_intake.models import BootstrapConfig, InboundMessage

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def main() -> int:
    exports = {
        "ws_message_v2.json": InboundMessage.model_json_schema(),
        "bootstrap_v1.json": BootstrapConfig.model_json_schema(),
    }
    for name, schema in exports.items():
        target = SCHEMAS / name
        target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
