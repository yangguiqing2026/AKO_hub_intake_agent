"""PII 检测与脱敏（data_access_level=PII_RESTRICTED）。"""

from __future__ import annotations

import re

_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_ID_CARD_PATTERN = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BANK_PATTERN = re.compile(r"(?<!\d)(\d{16,19})(?!\d)")


def mask_phone(match: re.Match[str]) -> str:
    return match.group(1)[:3] + "****" + match.group(1)[-4:]


def mask_id_card(match: re.Match[str]) -> str:
    return match.group(1)[:4] + "**********" + match.group(1)[-4:]


def mask_pii(text: str) -> str:
    """对电话、身份证、邮箱、银行卡号做脱敏。"""
    text = _PHONE_PATTERN.sub(mask_phone, text)
    text = _ID_CARD_PATTERN.sub(mask_id_card, text)
    text = _EMAIL_PATTERN.sub(_mask_email, text)
    text = _BANK_PATTERN.sub(lambda m: m.group(0)[:4] + "********" + m.group(0)[-4:], text)
    return text


def _mask_email(match: re.Match[str]) -> str:
    """邮箱脱敏：保留本地首字符与域名。"""
    local, _, domain = match.group(0).partition("@")
    return local[:1] + "***@" + domain


def contains_pii(text: str) -> bool:
    """判断文本是否包含 PII。"""
    return bool(
        _PHONE_PATTERN.search(text)
        or _ID_CARD_PATTERN.search(text)
        or _EMAIL_PATTERN.search(text)
        or _BANK_PATTERN.search(text)
    )
