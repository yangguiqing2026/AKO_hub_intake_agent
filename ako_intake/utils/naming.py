"""命名铁律校验（对齐 AKO_shared.naming 语义）。"""

from __future__ import annotations

import re

WO_PATTERN = re.compile(r"^WO-(DRAFT|HAI|LEG|AUD|QUA|SCH|DEP|SEC|PEN|REV|APL|PRE|VIO|FIX|APP)-(\d{8})-(\d{3,})$")
FILENAME_PATTERN = re.compile(r"^AKO_[a-z0-9_]+_v\d+\.\d+\.\d+\.md$")


def validate_wo_number(wo_number: str) -> bool:
    """校验工单号格式（WO-{模块缩写}-{YYYYMMDD}-{NNN}）。"""
    return bool(WO_PATTERN.match(wo_number))


def validate_filename(filename: str) -> bool:
    """校验体系文件名（AKO_{小写模块}_{小写描述}_vX.Y.Z.md）。"""
    return bool(FILENAME_PATTERN.match(filename))


def draft_wo_number(now: str = "", seq: int = 1) -> str:
    """生成草稿工单号 WO-DRAFT-YYYYMMDD-NNN。"""
    from datetime import datetime

    day = now or datetime.now().strftime("%Y%m%d")
    return f"WO-DRAFT-{day}-{seq:03d}"

