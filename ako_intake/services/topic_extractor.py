"""写作主题抽取（2026-09-14）。

writer 任务此前把**整句指令**当标题印在了文档上：实测文档
AKO_article_20260914_134919.docx 的标题位置是
「写一篇2000字的科技论文，主题是陶粒墙板在城市更新的运用。」整句，正文开头又重复一遍。

成因：intake 把整句 raw_input 直接塞进契约字段 `topic`，而 writer 侧
`n5_format.py` 拿 topic 兜底当标题。契约字段名叫 topic，传整句指令属契约违背。

本模块只做一件事：把用户指令里**真正的写作主题**取出来。抽不到就原样返回，
绝不报错——回退原句不更差于修复前的行为。
"""

from __future__ import annotations

import re

# 显式主题宣告：「主题是 X」「题目：X」
_DECLARED = re.compile(r"(?:主题|题目)\s*(?:是|为|：|:)\s*(.+)")
# 「以 X 为主题」
_AS_TOPIC = re.compile(r"以\s*(.+?)\s*(?:为主题|为题目)")
# 「关于 X 的<文体>」——「的」与文体词之间允许夹修饰语（如「的2000字论文」）
_ABOUT = re.compile(
    r"关于\s*(.+?)\s*的[^，,。；;]{0,8}?(?:文章|论文|报告|稿件|稿|文案|材料|东西)"
)

# 仅剥离主题末尾的标点与空白，不动主题内部标点
_TRAILING = re.compile(r"[\s。．.！!？?；;，,、]+$")


def extract_writing_topic(raw_input: str) -> str:
    """从写作指令中抽取写作主题；抽不到时原样返回 raw_input。

    优先级：显式宣告（主题是/题目：）> 「以 X 为主题」> 「关于 X 的」。
    """
    text = (raw_input or "").strip()
    if not text:
        return raw_input

    for pattern in (_DECLARED, _AS_TOPIC, _ABOUT):
        match = pattern.search(text)
        if match:
            topic = _TRAILING.sub("", match.group(1).strip())
            if topic.strip():
                return topic.strip()
    return raw_input
