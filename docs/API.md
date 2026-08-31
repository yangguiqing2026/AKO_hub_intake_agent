# AKO_hub_intake_agent API 契约

## Intake 服务（端口 5026）

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | /health | 存活与依赖探测 |
| GET | /metrics | 会话量、P0 轮次、投递成功率、Token 消耗 |
| GET | /api/v1/intake/sessions/{id} | 运行时状态查询 |
| POST | /api/v1/intake/review | M07 评审结果回写 |
| WS | /ws/intake | 看板实时通道（p0_interrogation / p0_response / wo_preview） |

## Hub 新增端点（:8080，标准库 HTTP）

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | /api/v1/hub/wo/allocate | 申请正式工单号 WO-HAI-*（TTL 300s） |
| POST | /api/v1/hub/wo/deliver | 投递 YAML/JSON 工单 |
| POST | /api/v1/hub/wo/manual_review | 低置信度工单入人工审核队列 |
| GET | /api/v1/hub/wo/{id} | 工单状态查询 |

## Registry 新增端点（:5024 Flask）

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | /ako/api/v1/registry/verify | 等级 + 信任边界校验（投递前门禁） |

## 投递链

```text
identity 认证 → registry verify（C 级/未评级拦截）→ hub allocate → deliver（幂等键 draft_wo_number）
→ ACK；Hub 不可达时入本地队列（eventual），指数退避重试
```

