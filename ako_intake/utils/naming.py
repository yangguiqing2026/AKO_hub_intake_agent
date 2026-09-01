"""命名铁律校验（对齐 AKO_shared.naming 语义）。"""

from __future__ import annotations

import re
import threading

WO_PATTERN = re.compile(r"^WO-(DRAFT|HAI|LEG|AUD|QUA|SCH|DEP|SEC|PEN|REV|APL|PRE|VIO|FIX|APP)-(\d{8})-(\d{3,})$")
FILENAME_PATTERN = re.compile(r"^AKO_[a-z0-9_]+_v\d+\.\d+\.\d+\.md$")

_UNIQUE_SEQ_LOCK = threading.Lock()
_LAST_UNIQUE_SEQ: int = 0


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


def unique_draft_wo_number() -> str:
    """生成当日唯一的草稿工单号（seq 取当日毫秒级时间戳，跨路径防碰撞，终审 C2）。

    draft_wo_number(seq) 的调用方传入 p0_rounds+1 等非唯一值，同日多会话会
    生成相同编号，破坏 Hub 幂等键与本地队列主键。
    同进程内以 _LAST_UNIQUE_SEQ 单调保护：连续调用落在同一毫秒时 +1 递补
    （当日最大 seq 235959999，+1 递补仍在 9 位宽度内）。
    """
    from datetime import datetime

    global _LAST_UNIQUE_SEQ
    now = datetime.now()
    with _UNIQUE_SEQ_LOCK:
        seq = int(now.strftime("%H%M%S")) * 1000 + now.microsecond // 1000
        if seq <= _LAST_UNIQUE_SEQ:
            seq = _LAST_UNIQUE_SEQ + 1
        _LAST_UNIQUE_SEQ = seq
    return f"WO-DRAFT-{now.strftime('%Y%m%d')}-{seq:09d}"

