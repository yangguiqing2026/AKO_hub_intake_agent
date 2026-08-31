"""PII 脱敏。"""

from __future__ import annotations

from ako_intake.utils.pii import contains_pii, mask_pii


def test_mask_phone() -> None:
    assert mask_pii("联系 13812345678 处理") == "联系 138****5678 处理"
    assert contains_pii("13812345678")


def test_mask_id_card_and_email() -> None:
    text = "身份证 110101199001011234，邮箱 a@b.com"
    masked = mask_pii(text)
    assert "1101**********1234" in masked
    assert "a***@b.com" in masked
    assert contains_pii(text)
    assert not contains_pii("没有敏感信息")

