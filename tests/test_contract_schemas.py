"""契约 schema 防漂移测试（FI-III-09，设计 7.2）。

schemas/ 文件由 scripts/export_contract_schemas.py 从 Pydantic 模型导出，
本测试保证已提交文件与导出结果一致。
"""

from __future__ import annotations

import json
from pathlib import Path

from ako_intake.models import BootstrapConfig, InboundMessage

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def _regenerate() -> dict[str, object]:
    return {
        "ws_message_v2.json": InboundMessage.model_json_schema(),
        "bootstrap_v1.json": BootstrapConfig.model_json_schema(),
    }


def test_committed_schemas_match_pydantic_export() -> None:
    for name, fresh in _regenerate().items():
        committed = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert committed == fresh, f"{name} 与 Pydantic 导出不一致，请运行 PYTHONPATH=. python scripts/export_contract_schemas.py"


def test_ws_schema_has_discriminator() -> None:
    schema = json.loads((SCHEMAS / "ws_message_v2.json").read_text(encoding="utf-8"))
    assert schema.get("discriminator", {}).get("propertyName") == "type"
