# AKO_hub_intake_agent 状态机说明

状态机由 `ako_intake/core/graph.py`（LangGraph StateGraph）驱动，与白皮书 v1.1.0 第八章一致。

| 状态码 | 状态名 | 说明 |
|:---|:---|:---|
| S00 | IDLE | 会话初始化，等待输入 |
| S10 | PARSING | M01 语义解析中 |
| S20 | AMBIGUITY_DETECTED | M02 歧义检测完成 |
| S22 | REVIEWING | M07 独立评审中 |
| S30 | CLARIFYING | M03 P0 反问中 |
| S40 | RESOLVED | 歧义清零 |
| S50 | FORM_BUILDING | M04 工单生成中 |
| S60 | VALIDATING | Schema 校验中 |
| S65 | QUEUED_LOCAL | Hub 不可达，工单入本地队列 |
| S70 | DELIVERED | 已投递 Hub 并获得 ACK |
| S80 | FAILED | 流程失败 |
| S85 | MANUAL_REVIEW | 人工审核队列 |
| S90 | ABANDONED | 用户放弃 |
| S95 | ARCHIVED | 终态归档 |

主干转换：

```text
START → parse(S10) → detect(S20) → [存在歧义] interrogate(S30) → detect
                                 → [无歧义] build(S50) → validate(S60) → review(S22)
review → [score>=0.9] deliver(S70) → END
       → [score<0.9 且未人工确认] manual_review(S85) → END
deliver → [Hub 不可达] queued_local(S65) → END
异常路径 → fail(S80) → END
```

