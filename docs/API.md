# AKO_hub_intake_agent API 契约（v2）

> 本文档定义 Intake 后端（FastAPI，:5026）对外接口契约：WS v2 消息协议 + REST 端点。
> 与《AKO_hub_intake_frontend_contract_v1.0.0.md》第三章保持一致（以该设计文档为绑定权威）。

## 端口约定

| 服务 | 端口 | 说明 |
|:---|:---|:---|
| Intake 后端 | 5026 | WS v2 + REST，与白皮书 6.6 一致 |
| 前端 dev server | 5027 | vite proxy（/ws、/api）→ 5026 |
| hub / registry / knowledge | 8080 / 5024 / 8000 | 仅后端出站，前端不直连 |
| identity | 按 secrets.env | 仅后端出站；未配置时后端返回开发态模拟令牌（仅限非生产） |

---

## WS v2 通道（/ws/intake）

所有 WS 双向消息统一信封：

```json
{
  "v": 2,
  "type": "p0_interrogation",
  "req_id": "req-<uuid>",
  "session_id": "sess-20260901-001",
  "seq": 42,
  "ts": "2026-09-01T10:35:00+08:00",
  "payload": {}
}
```

| 字段 | 方向 | 说明 |
|:---|:---|:---|
| `v` | 双 | 协议版本，恒为 2；不匹配 → `error(PROTOCOL_VERSION_MISMATCH)` |
| `type` | 双 | 消息类型，须在下方白名单内 |
| `req_id` | 双 | 可选。请求-响应关联：服务端对入站请求的应答回填相同 `req_id` |
| `session_id` | 双 | 会话标识；`auth`/`ping` 阶段可为空 |
| `seq` | S→C | 服务端按会话单调递增序号，从 1 起 |
| `ts` | S→C | 服务端时间戳 ISO8601 |
| `payload` | 双 | 各类型的判别联合负载 |

### 入站消息（C→S，10 类，服务端白名单 + Pydantic 校验）

| type | payload | 状态机对应 | 说明 |
|:---|:---|:---|:---|
| `auth` | `{token}` | 连接建立 | 连接后首条消息（超时未发即断开）；令牌经 identity 校验后绑定会话身份，失败回 `error(AUTH_REQUIRED)` |
| `intake_input` | `{text}` | S00→S10 | 文本 10~2000 字符；超限回 `error(TEXT_TOO_LONG/TEXT_TOO_SHORT)` |
| `p0_response` | `{round, answers[{qid,value}], conservative?}` | S30→S20 | `conservative: true` = 用户选择"按最保守策略处理"，触发 7.1 降级路径 |
| `wo_edit` | `{draft_wo: {部分字段}}` | S50 人工微调 | 回写后重跑 validate（S60）与 M07 评审（S22），重置人工确认（human_confirmed=false，旧确认不穿透新草稿），再发 `wo_preview`；校验失败回 `error(SCHEMA_ERROR)` |
| `wo_confirm` | `{}` | S22/S50→S70 | 确认投递，走三重门禁链路（见"投递链"）；registry 拦截分支无前置 status 事件（Phase B 前端须知） |
| `wo_discard` | `{}` | →IDLE | 放弃当前工单（清空草稿回 IDLE；放弃整个会话用 `session_abandon`） |
| `session_resume` | `{session_id}` | 断点续传 | 服务端回 `session_snapshot`；会话不存在回 `error(SESSION_NOT_FOUND)` |
| `session_abandon` | `{}` | →S90 | 放弃整个会话，回 `status{status:"ABANDONED"}` |
| `stream_ack` | `{stream_id, bytes}` | — | 分片流控确认（每累计 16KB 一次） |
| `ping` | `{}` | — | 心跳（默认 30s 一次），回 `pong` |

### 出站消息（S→C，14 类）

| type | payload | 说明 |
|:---|:---|:---|
| `hello` | `{protocol_version: 2, server_time, session_id, bootstrap}` | `auth` 通过后即发（含 BootstrapConfig）；快照不随 hello 下发，经 `session_resume` → `session_snapshot` 通道获取 |
| `session_snapshot` | `{state, seq}` | 全量快照（续传/gap 修复时下发） |
| `status` | `{status, detail?}` | 轻量状态迁移通知（PARSING/IDLE/ABANDONED 等） |
| `p0_interrogation` | `{round, questions[], timeout_seconds, expires_at}` | S30 反问卡片（每轮 ≤3 问） |
| `p0_timeout` | `{round}` | 单轮反问超时提醒（后端到点仍执行 7.1 保守降级）；Phase A 仅契约预留，Phase D 实现 |
| `wo_preview` | `{draft_wo, confidence_score, review_record?, risk_flag?, actions}` | S50/S22 工单预览；`draft_wo` 出站前经 PII 脱敏 |
| `review_result` | `{review_record}` | M07 评审结果（独立推送，供评审面板单独渲染） |
| `hub_ack` | `{ack}` | S70 投递回执（正式编号/hub_trace_id/队列位置） |
| `queued_local` | `{wo_number, next_retry_at}` | S65 Hub 不可达入本地队列 |
| `manual_review` | `{draft_wo, reason}` | S85 入人工审核队列（reason 如 `REGISTRY_BLOCKED`/`P0_MAX_ROUNDS_EXCEEDED`） |
| `stream_chunk` | `{stream_id, kind: "start"\|"chunk"\|"end", data}` | 分片流帧（3.4）；`use_llm=false`（当前配置）时无此帧 |
| `soft_break` | `{usage_percent, monthly_quota_tokens, active}` | 预算软熔断状态消息（7.6）：`active=true` 触发（升横幅 + 强制专家模式）、`active=false` 解除（配额上调即时推送）；解除亦经 hello/bootstrap 快照 `soft_break_active=false` 对账 |
| `error` | `{code, message}` | 见"错误码"表 |
| `pong` | `{}` | 心跳应答 |

### 序号与快照机制

- 服务端为每个会话维护 `seq` 计数器（进程内存，会话状态本身在 SQLite），每条 S→C 消息 `seq` 自增。
- 客户端镜像规则：`seq <= last_seq` 丢弃；`== last_seq+1` 应用；`> last_seq+1` 检测到 gap → 丢弃该消息并发 `session_resume` 索取 `session_snapshot`。
- `session_snapshot` 无条件接受：`last_seq = snapshot.seq`，整个镜像以快照重建。

### 分片流式帧

- 帧序列：一个 `stream_id` 对应 `start → chunk* → end`，缺序即丢弃整个流。
- 流控：客户端每累计 16KB 发一次 `stream_ack {stream_id, bytes}`；服务端连续未收到 ack 时暂停发送。
- 降级：`use_llm=false`（当前配置）时无 `stream_chunk`，进度以 `status` 事件为主驱动。

---

## REST 端点

### 保留端点

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | /health | 存活与依赖探测（hub/registry/identity/knowledge），负载不变 |
| GET | /metrics | 增强：在现有快照基础上并入 `budget`（usage_by_caller/usage_percent）与 `queue`（本地队列 stats） |
| GET | /api/v1/intake/sessions/{id} | 运行时状态查询（调试/对账），不存在回 404 |
| POST | /api/v1/intake/review | M07 评审结果回写（`session_id`/`review_score`/`human_confirmed`），负载不变 |

### 新增端点

| 方法 | 路径 | 请求 | 响应要点 |
|:---|:---|:---|:---|
| GET | /api/v1/bootstrap | — | 引导配置：`{agent_id, version, terms[], intake{...}, budget{...}, llm{...}, knowledge_enabled, identity_required, ws{...}, observability{sentry_dsn}}` |
| GET | /api/v1/intake/sessions | — | 会话列表：非终态全量 + 最近 7 天终态，供续传选择页 |
| POST | /api/v1/intake/sessions | `{raw_text?}` 或 `{draft_wo?}` | `{session_id, status}`。`raw_text` 走自然语言链路（S00 起）；`draft_wo` 走专家模式（跳过 S10~S30，直接以 draft_wo 进入 S50 评审，随后经 WS 发 `wo_preview`）；draft_wo 校验失败回 400 schema_error |
| POST | /api/v1/intake/sessions/{id}/abandon | — | `{session_id, status: "ABANDONED"}` |
| GET | /api/v1/intake/queue/stats | — | 本地投递队列统计：`{pending, done, failed}`（由 CLI `cmd_queue` 升为 HTTP） |
| POST | /api/v1/intake/queue/flush | — | 手动冲刷本地队列：`{flushed: [wo_number...]}` |
| POST | /api/v1/identity/login | `{account, fingerprint}` | 登录代理：`{token, expires_at, identity:{account}}`；identity 地址未配置时返回开发态令牌（仅限非生产） |
| POST | /api/v1/identity/verify | `{token}` | 令牌校验代理：`{valid, identity}` |

鉴权约定：REST 统一 `Authorization: Bearer <token>`；失败回 401。

---

## Hub 端点（:8080，标准库 HTTP）

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | /api/v1/hub/wo/allocate | 申请正式工单号 WO-HAI-*（TTL 300s） |
| POST | /api/v1/hub/wo/deliver | 投递 YAML/JSON 工单（幂等键 draft_wo_number） |
| POST | /api/v1/hub/wo/manual_review | 低置信度工单入人工审核队列 |
| GET | /api/v1/hub/wo/{id} | 工单状态查询 |

## Registry 端点（:5024 Flask）

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | /ako/api/v1/registry/verify | 等级 + 信任边界校验（投递前门禁；C 级/未评级拦截，仅 registry 已配置时） |

---

## 投递链（wo_confirm 三重门禁）

```text
wo_confirm
→ registry verify（第二重门禁；C 级/未评级 → manual_review{reason: REGISTRY_BLOCKED}，仅 registry 已配置时拦截）
→ hub allocate（申请正式编号 WO-HAI-*）
→ hub deliver（幂等键 draft_wo_number）
→ ACK → hub_ack{ack: {wo_number, queue_position, hub_trace_id}}
→ Hub 不可达时入本地队列（queued_local，S65，eventual，指数退避重试）
```

三重门禁总览（白皮书 A.5 的接口面）：

| 门禁 | 接口面 | 后端动作 |
|:---|:---|:---|
| 第一重 身份 | 登录页 → `POST /api/v1/identity/login` 换 token；REST `Authorization: Bearer`；WS 首消息 `auth` | 经 `POST /api/v1/identity/verify` 代理校验，失败回 `error(AUTH_REQUIRED)` / HTTP 401 |
| 第二重 等级 | `wo_confirm` 链路内 | registry verify 拦 C 级/未评级目标，拦截结果以 `manual_review` 呈现 |
| 第三重 数据 | 出站负载 | `mask_pii` 对 `wo_preview.draft_wo` 全字符串字段脱敏 |

前端不接触 hub/registry 凭证，全部由后端代理。

---

## 错误码

| code | 触发 |
|:---|:---|
| `PROTOCOL_VERSION_MISMATCH` | `v` ≠ 2 |
| `INVALID_MESSAGE_TYPE` | 入站 type 不在白名单（连接不中断） |
| `INVALID_PAYLOAD` | Pydantic 校验失败 |
| `AUTH_REQUIRED` | 未 auth 即发业务消息 / token 失效 |
| `SESSION_NOT_FOUND` | resume/操作不存在的会话 |
| `TEXT_TOO_SHORT` / `TEXT_TOO_LONG` | 文本 <10 / >2000 字符 |
| `P0_MAX_ROUNDS` | 超 3 轮仍未清零（以 `manual_review` 呈现） |
| `P0_TIMEOUT` | 单轮超时（以降级结果呈现） |
| `SCHEMA_ERROR` | 工单校验失败（含 REST 400 schema_error） |
| `HUB_UNREACHABLE` | Hub 不可达（以 `queued_local` 呈现，S65） |
| `SOFT_BREAK_ACTIVE` | 预算软熔断中（以 `soft_break` 呈现） |
| `INTERNAL` | 未归类异常 |
