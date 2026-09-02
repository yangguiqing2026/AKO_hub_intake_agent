# 前端五视图实现计划（Phase B–E）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 AKO_hub_intake_agent 纯 Web 看板前端（五视图 + 暖金设计系统 + WS v2 客户端 + Zustand 状态镜像），消费 Phase A 已冻结的 WS v2 / REST 契约，达到设计文档第四章界面规格与第七章验收标准。

**Architecture:** React 18 + TS(strict) + Vite 的 SPA；`web/src/schemas/`（zod 判别联合，双端契约事实测试）→ `web/src/api/`（ws.ts 传输层 + rest.ts REST 客户端）→ `web/src/store/`（5 个 Zustand slice，sessionStore 按设计 3.3 实现 seq 镜像规则）→ `web/src/hooks/useIntakeSocket.ts`（连接编排 + 消息路由）→ 5 视图 + AppShell。后端契约已冻结（Phase A 合入 main @ 9ed858e），本计划**不修改任何后端文件**。

**Tech Stack:** React 18.3 / TypeScript 5.5（strict）/ Vite 5 / Zustand 4 / zod 3.23 + zod-to-json-schema / vitest 2 + jsdom。

**Spec:** `docs/AKO_hub_intake_frontend_contract_v1.0.0.md`（绑定权威：第四章界面、第五章时序、第六章错误处理、第七章测试验收、第八章 Phase B–E 改动清单）。

## Global Constraints

- **后端冻结**：不修改 `ako_intake/*`、`app.py`、`schemas/*`、`config/*`。契约以 `docs/API.md` + `schemas/ws_message_v2.json` + `schemas/bootstrap_v1.json` 为准；前端发现契约缺陷 → 报告控制器裁定（不得自行改后端）。
- **契约事实（前端必须精确消费，均来自已实现后端）**：
  - 信封 `v: 2` 恒等；入站 10 类（auth/intake_input/p0_response/wo_edit/wo_confirm/wo_discard/session_resume/session_abandon/stream_ack/ping）；出站 14 类（hello/session_snapshot/status/p0_interrogation/p0_timeout/wo_preview/review_result/hub_ack/queued_local/manual_review/stream_chunk/soft_break/error/pong）。
  - `seq` 按会话单调递增、从 1 起；镜像规则：`seq <= last_seq` 丢弃；`seq == last_seq+1` 应用；`seq > last_seq+1` 判 gap → 发 `session_resume` → 收 `session_snapshot{state, seq}` 全量重建。
  - `hello` 不携带 snapshot（快照统一走 resume 通道）；`wo_discard` 回 IDLE；`session_abandon` 才到 S90。
  - REST：`POST /api/v1/identity/login{account, fingerprint}` → `{token, expires_at, identity}`；`GET /api/v1/bootstrap`；`GET/POST /api/v1/intake/sessions`；`POST /api/v1/intake/sessions/{id}/abandon`；`GET /api/v1/intake/queue/stats`；`POST /api/v1/intake/queue/flush`；`GET /metrics`；`POST /api/v1/intake/review{session_id, review_score, human_confirmed}`。REST 需 `Authorization: Bearer <token>`（dev 态后端放行）；401 → 跳登录。
  - 出站负载中的 PII 已由后端 `mask_pii` 脱敏（前端展示"已脱敏"徽章，不做二次处理）。
  - 端口：dev server :5027，vite proxy `/ws`、`/api` → :5026（既有配置，保留）。
- **编码规范（全局 CLAUDE.md）**：所有函数必须有类型注解；优先函数式；新增工具函数必须写单测；TS strict + noUnusedLocals/Parameters。
- **替换清单**：删除 `web/src/api/client.ts`(+`client.test.ts`)、`web/src/store/useSessionStore.ts`(+test)；升级 `web/src/components/QuestionCard.tsx`、`WoPreviewCard.tsx`；重构 `web/src/pages/IntakePage.tsx`；接入 `ExpertPage.tsx`；`App.tsx` → AppShell。`web/src/main.tsx`、`index.html`、`vite.config.ts`（proxy）不动（除 F2 环境变量读取外）。
- **验收映射**：AC-11 首屏 ≤1.5s（无 UI 库依赖、单 tokens.css）、AC-13 反问卡渲染 ≤200ms（WS 直达 store）、AC-07/08/27 场景前端呈现（queued_local 卡/续传恢复/软熔断横幅）。

---

### Task 1: zod schema 层与双端契约事实测试

**Files:**
- Modify: `web/package.json`（新增依赖）
- Create: `web/src/schemas/ws.ts`、`web/src/schemas/ws.contract.test.ts`
- Test: `web/src/schemas/ws.contract.test.ts`

**Interfaces:**
- Consumes: `schemas/ws_message_v2.json`、`schemas/bootstrap_v1.json`（后端已提交的契约事实源）。
- Produces:
  - `inboundEnvelope: z.ZodDiscriminatedUnion`（入站 10 类，判别器 `type`）
  - `outboundEnvelope: z.ZodDiscriminatedUnion`（出站 14 类）
  - `question`、`reviewRecord`、`bootstrapConfig` zod schema
  - `type OutboundMessage = z.infer<typeof outboundEnvelope>`、`type Question`、`type BootstrapConfig`
  - 契约事实函数 `contractFacts(schema: unknown): ContractFacts`（供测试与后续任务复用）

- [ ] **Step 1: 安装依赖**

```bash
cd web
npm install zod@^3.23.8 zod-to-json-schema@^3.23.2
```

- [ ] **Step 2: 写失败测试（契约事实比对）**

创建 `web/src/schemas/ws.contract.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { toJsonSchema } from "zod-to-json-schema";
import { inboundEnvelope, outboundEnvelope } from "./ws";

const SCHEMAS_DIR = new URL("../../../schemas/", import.meta.url);

interface ContractFacts {
  types: string[];          // 判别联合的消息类型名（按出现序）
  requiredByType: Record<string, string[]>; // 每类型必填字段（去默认值）
  textBounds?: { min: number; max: number }; // intake_input.text 边界
  roundMin?: number;        // p0_response.round 下界
}

function requiredFromPydantic(schema: unknown, typeName: string): string[] {
  // pydantic 导出：oneOf[i].$ref → $defs[name].required
  const s = schema as { oneOf?: { $ref?: string }[]; $defs?: Record<string, { required?: string[]; properties?: Record<string, unknown> }> };
  const entry = s.oneOf?.find((o) => {
    const name = (o.$ref ?? "").split("/").pop() ?? "";
    const def = s.$defs?.[name];
    return def?.properties?.type && (def.properties.type as { const?: string }).const === typeName;
  });
  const name = (entry?.$ref ?? "").split("/").pop() ?? "";
  return s.$defs?.[name]?.required ?? [];
}

function requiredFromZod(schema: unknown, typeName: string): string[] {
  const s = schema as { oneOf?: { properties?: { type?: { const?: string }; payload?: { properties?: Record<string, { type?: string; default?: unknown }> } } } }[];
  const entry = s.oneOf?.find((o) => o.properties?.type?.const === typeName);
  const props = entry?.properties?.payload?.properties ?? {};
  return Object.entries(props).filter(([, v]) => v.default === undefined).map(([k]) => k);
}

describe("双端契约事实（设计 7.2）", () => {
  const pydantic = JSON.parse(readFileSync(new URL("ws_message_v2.json", SCHEMAS_DIR), "utf-8"));
  const zodInbound = toJsonSchema(inboundEnvelope);

  it("入站消息类型集合与后端一致（10 类）", () => {
    const pydTypes = (pydantic.oneOf as { $ref: string }[]).map((o) =>
      (pydantic.$defs[(o.$ref as string).split("/").pop()!].properties.type as { const: string }).const,
    );
    const zodTypes = (zodInbound.oneOf as { properties: { type: { const: string } } }[]).map((o) => o.properties.type.const);
    expect(zodTypes).toEqual(pydTypes);
    expect(zodTypes).toHaveLength(10);
  });

  it("auth/intake_input/p0_response 必填字段双端一致", () => {
    for (const t of ["auth", "intake_input", "p0_response"]) {
      expect(requiredFromZod(zodInbound, t).sort()).toEqual(requiredFromPydantic(pydantic, t).sort());
    }
  });

  it("intake_input.text 边界 10..2000 双端一致", () => {
    const findText = (s: unknown): { min: number; max: number } => {
      const oneOf = (s as { oneOf: { properties: { type: { const: string }; payload: { properties: { text: { minLength?: number; maxLength?: number } } } } }[] }).oneOf;
      const entry = oneOf.find((o) => o.properties.type.const === "intake_input")!;
      const t = entry.properties.payload.properties.text;
      return { min: t.minLength!, max: t.maxLength! };
    };
    expect(findText(zodInbound)).toEqual(findText(pydantic));
    expect(findText(zodInbound)).toEqual({ min: 10, max: 2000 });
  });
});
```

- [ ] **Step 3: 运行测试确认失败**

Run: `npm test -- --run src/schemas/ws.contract.test.ts`
Expected: FAIL，`Cannot find module './ws'`

- [ ] **Step 4: 实现 zod schema 层**

创建 `web/src/schemas/ws.ts`：

```ts
import { z } from "zod";

// ---- 入站（C→S）----
const envelope = z.object({ v: z.literal(2).default(2), req_id: z.string().default(""), session_id: z.string().default("") });

export const authPayload = z.object({ token: z.string().min(1) });
export const intakeInputPayload = z.object({ text: z.string().min(10).max(2000) });
export const answerItem = z.object({ qid: z.string(), value: z.string() });
export const p0ResponsePayload = z.object({
  round: z.number().int().min(1),
  answers: z.array(answerItem).default([]),
  conservative: z.boolean().default(false),
});
export const woEditPayload = z.object({ draft_wo: z.record(z.string(), z.unknown()).default({}) });
export const sessionResumePayload = z.object({ session_id: z.string().min(1) });
export const streamAckPayload = z.object({ stream_id: z.string(), bytes: z.number().int().min(0) });
export const emptyPayload = z.object({});

export const inboundEnvelope = z.discriminatedUnion("type", [
  z.object({ ...envelope.shape, type: z.literal("auth"), payload: authPayload }),
  z.object({ ...envelope.shape, type: z.literal("intake_input"), payload: intakeInputPayload }),
  z.object({ ...envelope.shape, type: z.literal("p0_response"), payload: p0ResponsePayload }),
  z.object({ ...envelope.shape, type: z.literal("wo_edit"), payload: woEditPayload }),
  z.object({ ...envelope.shape, type: z.literal("wo_confirm"), payload: emptyPayload }),
  z.object({ ...envelope.shape, type: z.literal("wo_discard"), payload: emptyPayload }),
  z.object({ ...envelope.shape, type: z.literal("session_resume"), payload: sessionResumePayload }),
  z.object({ ...envelope.shape, type: z.literal("session_abandon"), payload: emptyPayload }),
  z.object({ ...envelope.shape, type: z.literal("stream_ack"), payload: streamAckPayload }),
  z.object({ ...envelope.shape, type: z.literal("ping"), payload: emptyPayload }),
]);
export type InboundEnvelope = z.infer<typeof inboundEnvelope>;

// ---- 出站（S→C）----
export const question = z.object({
  qid: z.string(), field: z.string(), text: z.string(),
  type: z.enum(["single_choice", "open", "confirm"]),
  options: z.array(z.string()).default([]),
  required: z.boolean().default(true),
});
export const reviewRecord = z.object({
  review_score: z.number(), structural_passed: z.boolean().default(true),
  differences: z.array(z.string()).default([]), reviewed_at: z.string().default(""),
});
export const bootstrapConfig = z.object({
  agent_id: z.string(), version: z.string(),
  terms: z.array(z.object({ term: z.string(), module: z.string(), actions: z.array(z.string()) })),
  intake: z.record(z.string(), z.unknown()), budget: z.record(z.string(), z.unknown()),
  llm: z.record(z.string(), z.unknown()), knowledge_enabled: z.boolean(),
  identity_required: z.boolean(), ws: z.record(z.string(), z.unknown()),
  observability: z.record(z.string(), z.unknown()),
});

const outEnvelope = { v: z.literal(2), req_id: z.string().default(""), session_id: z.string(), seq: z.number().int().min(1), ts: z.string() };
export const outboundEnvelope = z.discriminatedUnion("type", [
  z.object({ ...outEnvelope, type: z.literal("hello"), payload: z.object({ protocol_version: z.number(), server_time: z.string(), session_id: z.string(), bootstrap: bootstrapConfig }) }),
  z.object({ ...outEnvelope, type: z.literal("session_snapshot"), payload: z.object({ state: z.record(z.string(), z.unknown()), seq: z.number().int().min(1) }) }),
  z.object({ ...outEnvelope, type: z.literal("status"), payload: z.object({ status: z.string(), detail: z.string().optional() }) }),
  z.object({ ...outEnvelope, type: z.literal("p0_interrogation"), payload: z.object({ round: z.number().int().min(1), questions: z.array(question), timeout_seconds: z.number(), expires_at: z.string() }) }),
  z.object({ ...outEnvelope, type: z.literal("p0_timeout"), payload: z.object({ round: z.number().int() }) }),
  z.object({ ...outEnvelope, type: z.literal("wo_preview"), payload: z.object({ draft_wo: z.record(z.string(), z.unknown()), confidence_score: z.number(), review_record: reviewRecord.optional(), risk_flag: z.string().default(""), actions: z.array(z.enum(["confirm", "edit", "discard"])).default(["confirm", "edit", "discard"]) }) }),
  z.object({ ...outEnvelope, type: z.literal("review_result"), payload: z.object({ review_record: reviewRecord }) }),
  z.object({ ...outEnvelope, type: z.literal("hub_ack"), payload: z.object({ ack: z.record(z.string(), z.unknown()) }) }),
  z.object({ ...outEnvelope, type: z.literal("queued_local"), payload: z.object({ wo_number: z.string(), next_retry_at: z.string() }) }),
  z.object({ ...outEnvelope, type: z.literal("manual_review"), payload: z.object({ draft_wo: z.record(z.string(), z.unknown()), reason: z.string() }) }),
  z.object({ ...outEnvelope, type: z.literal("stream_chunk"), payload: z.object({ stream_id: z.string(), kind: z.enum(["start", "chunk", "end"]), data: z.unknown() }) }),
  z.object({ ...outEnvelope, type: z.literal("soft_break"), payload: z.object({ usage_percent: z.number(), monthly_quota_tokens: z.number() }) }),
  z.object({ ...outEnvelope, type: z.literal("error"), payload: z.object({ code: z.string(), message: z.string() }) }),
  z.object({ ...outEnvelope, type: z.literal("pong"), payload: emptyPayload }),
]);
export type OutboundMessage = z.infer<typeof outboundEnvelope>;
export type Question = z.infer<typeof question>;
export type ReviewRecord = z.infer<typeof reviewRecord>;
export type BootstrapConfig = z.infer<typeof bootstrapConfig>;
```

注意：zod 的 `v: z.literal(2)` 在入站用 `.default(2)`、出站必填——与后端 `WSEnvelopeMixin.v: Literal[2] = 2`（入站默认）及出站必填语义一致；`contractFacts` 命名在测试中以内联函数实现（跨任务不复用，避免过早抽象）。

- [ ] **Step 5: 运行测试确认通过**

Run: `npm test -- --run src/schemas/ws.contract.test.ts`
Expected: PASS（3 用例；若 pydantic 的 $defs 结构或 zod-to-json-schema 输出与预期有差异，调整测试中的提取函数而非 schema——schema 以双端一致性为准，差异须报告控制器）

- [ ] **Step 6: 提交**

```bash
git add web/package.json web/package-lock.json web/src/schemas/ws.ts web/src/schemas/ws.contract.test.ts
git commit -m "feat(web): zod 契约层与双端契约事实测试"
```

---

### Task 2: API 客户端层（ws.ts 传输 + rest.ts）

**Files:**
- Create: `web/src/api/ws.ts`、`web/src/api/rest.ts`
- Delete: `web/src/api/client.ts`、`web/src/api/client.test.ts`
- Test: `web/src/api/ws.test.ts`、`web/src/api/rest.test.ts`

**Interfaces:**
- Consumes: F1 的 `outboundEnvelope`/`OutboundMessage`。
- Produces:
  - `class IntakeSocket`（选项 `{url, onMessage, onStateChange?, onOpen?, heartbeatSeconds?, streamAckBytes?, maxBackoffSeconds?}`；方法 `connect()/send(type, sessionId, payload?): boolean/close()`）
  - `createRestClient({baseUrl, getToken, onUnauthorized})` → `{get<T>(path), post<T>(path, body?)}`；`class ApiError extends Error {code: number}`

- [ ] **Step 1: 写失败测试**

创建 `web/src/api/ws.test.ts`：

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IntakeSocket } from "./ws";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) { FakeWebSocket.instances.push(this); }
  send(data: string): void { this.sent.push(data); }
  close(): void { this.readyState = 3; this.onclose?.(); }
  static openLatest(): void { const w = FakeWebSocket.instances.at(-1)!; w.readyState = 1; w.onopen?.(); }
  static emit(ws: FakeWebSocket, data: string): void { ws.onmessage?.({ data }); }
}

beforeEach(() => { FakeWebSocket.instances = []; vi.stubGlobal("WebSocket", FakeWebSocket); vi.useFakeTimers(); });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("IntakeSocket", () => {
  it("连接后按信封解析出站消息并回调", () => {
    const onMessage = vi.fn();
    const s = new IntakeSocket({ url: "ws://x", onMessage });
    s.connect();
    FakeWebSocket.openLatest();
    FakeWebSocket.emit(FakeWebSocket.instances[0], JSON.stringify({ v: 2, type: "status", session_id: "s1", seq: 1, ts: "t", payload: { status: "PARSING" } }));
    expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({ type: "status", seq: 1 }));
  });

  it("解析失败的消息被静默丢弃（不断连）", () => {
    const onMessage = vi.fn();
    const s = new IntakeSocket({ url: "ws://x", onMessage });
    s.connect();
    FakeWebSocket.openLatest();
    FakeWebSocket.emit(FakeWebSocket.instances[0], "not-json");
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("断线指数退避重连（1s→2s→4s，封顶 30s）", () => {
    const onStateChange = vi.fn();
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn(), onStateChange });
    s.connect();
    FakeWebSocket.openLatest();
    FakeWebSocket.instances[0].close(); // onclose → 退避重连
    expect(onStateChange).toHaveBeenCalledWith("reconnecting");
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(2000);
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it("close() 后不再重连", () => {
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn() });
    s.connect();
    FakeWebSocket.openLatest();
    s.close();
    vi.advanceTimersByTime(100000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("退避窗口内 close() 取消待触发重连（修复轮 1 覆盖）", () => {
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn() });
    s.connect();
    FakeWebSocket.openLatest();
    FakeWebSocket.instances[0].close(); // 触发退避调度（1s）
    s.close();                          // 退避窗口内关闭
    vi.advanceTimersByTime(100000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("send 按 v2 信封发送；未连接时返回 false", () => {
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn() });
    expect(s.send("ping", "")).toBe(false);
    s.connect();
    FakeWebSocket.openLatest();
    expect(s.send("intake_input", "s1", { text: "修复报价模块的bug，只动校验逻辑，不动数据库" })).toBe(true);
    expect(JSON.parse(FakeWebSocket.instances[0].sent[0])).toEqual({ v: 2, type: "intake_input", session_id: "s1", payload: { text: "修复报价模块的bug，只动校验逻辑，不动数据库" } });
  });

  it("stream_chunk 累计 16KB 自动发 stream_ack", () => {
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn(), streamAckBytes: 5 });
    s.connect();
    FakeWebSocket.openLatest();
    const ws = FakeWebSocket.instances[0];
    const big = "x".repeat(6);
    FakeWebSocket.emit(ws, JSON.stringify({ v: 2, type: "stream_chunk", session_id: "s1", seq: 1, ts: "t", payload: { stream_id: "st1", kind: "chunk", data: big } }));
    const ack = ws.sent.find((m) => JSON.parse(m).type === "stream_ack");
    expect(ack).toBeDefined();
    expect(JSON.parse(ack!).payload.bytes).toBeGreaterThanOrEqual(5);
  });
});
```

创建 `web/src/api/rest.test.ts`：

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createRestClient } from "./rest";

describe("createRestClient", () => {
  beforeEach(() => { vi.stubGlobal("fetch", vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("携带 Bearer 头并解析 JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    const client = createRestClient({ baseUrl: "http://x", getToken: () => "tok", onUnauthorized: vi.fn() });
    await expect(client.get<{ ok: number }>("/api/v1/bootstrap")).resolves.toEqual({ ok: 1 });
    expect(fetch).toHaveBeenCalledWith("http://x/api/v1/bootstrap", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer tok" }) }));
  });

  it("401 → ApiError 并触发 onUnauthorized", async () => {
    const onUnauthorized = vi.fn();
    vi.mocked(fetch).mockResolvedValue(new Response("", { status: 401 }));
    const client = createRestClient({ baseUrl: "http://x", getToken: () => "tok", onUnauthorized });
    await expect(client.get("/api/v1/intake/sessions")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("POST 序列化 body", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 200 }));
    const client = createRestClient({ baseUrl: "http://x", getToken: () => "", onUnauthorized: vi.fn() });
    await client.post("/api/v1/identity/login", { account: "a", fingerprint: "123456" });
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(init!.body as string)).toEqual({ account: "a", fingerprint: "123456" });
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/api`
Expected: FAIL，`Cannot find module './ws'` / `'./rest'`

- [ ] **Step 3: 实现 ws.ts 与 rest.ts**

创建 `web/src/api/ws.ts`：

```ts
import { outboundEnvelope, type OutboundMessage } from "../schemas/ws";

export interface IntakeSocketOptions {
  url: string;
  onMessage: (msg: OutboundMessage) => void;
  onStateChange?: (state: "connecting" | "open" | "reconnecting" | "closed") => void;
  onOpen?: () => void;
  heartbeatSeconds?: number;
  streamAckBytes?: number;
  maxBackoffSeconds?: number;
}

export class IntakeSocket {
  private ws: WebSocket | null = null;
  private backoffMs = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null; // 修复轮：退避定时器可取消
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private closedByUser = false;
  private streamBytes = 0;
  private streamId = "";

  constructor(private readonly opts: IntakeSocketOptions) {}

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  close(): void {
    this.closedByUser = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) { // 修复轮：退避窗口内关闭必须取消待触发重连
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.opts.onStateChange?.("closed");
  }

  send(type: string, sessionId: string, payload: Record<string, unknown> = {}): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify({ v: 2, type, session_id: sessionId, payload }));
    return true;
  }

  private open(): void {
    this.opts.onStateChange?.(this.ws ? "reconnecting" : "connecting");
    const ws = new WebSocket(this.opts.url);
    this.ws = ws;
    ws.onopen = (): void => {
      this.opts.onStateChange?.("open");
      this.backoffMs = 1000;
      this.startHeartbeat();
      this.opts.onOpen?.();
    };
    ws.onmessage = (e: MessageEvent<string>): void => this.handleRaw(e.data);
    ws.onclose = (): void => {
      this.stopHeartbeat();
      if (this.closedByUser) return;
      this.scheduleReconnect();
    };
    ws.onerror = (): void => ws.close();
  }

  private scheduleReconnect(): void {
    this.opts.onStateChange?.("reconnecting");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.closedByUser) return; // 修复轮：双保险，close() 后回调不再重连
      this.open();
    }, this.backoffMs);
    this.backoffMs = Math.min(this.backoffMs * 2, (this.opts.maxBackoffSeconds ?? 30) * 1000);
  }

  private handleRaw(raw: string): void {
    let msg: OutboundMessage;
    try {
      msg = outboundEnvelope.parse(JSON.parse(raw));
    } catch {
      return;
    }
    if (msg.type === "stream_chunk") {
      this.trackStream(msg.payload.stream_id, String(msg.payload.data ?? "").length, msg.payload.kind);
    }
    if (msg.type === "pong") return;
    this.opts.onMessage(msg);
  }

  private trackStream(streamId: string, bytes: number, kind: "start" | "chunk" | "end"): void {
    if (kind === "start") { this.streamId = streamId; this.streamBytes = 0; return; }
    if (kind === "end") { this.streamBytes = 0; return; }
    this.streamBytes += bytes;
    if (this.streamBytes >= (this.opts.streamAckBytes ?? 16384)) {
      this.send("stream_ack", "", { stream_id: this.streamId || streamId, bytes: this.streamBytes });
      this.streamBytes = 0;
    }
  }

  private startHeartbeat(): void {
    const hb = (this.opts.heartbeatSeconds ?? 30) * 1000;
    this.heartbeatTimer = setInterval(() => { this.send("ping", ""); }, hb);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }
}
```

创建 `web/src/api/rest.ts`：

```ts
export class ApiError extends Error {
  constructor(public readonly code: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RestClientOptions {
  baseUrl: string;
  getToken: () => string;
  onUnauthorized?: () => void;
}

export function createRestClient(opts: RestClientOptions): { get: <T>(path: string) => Promise<T>; post: <T>(path: string, body?: unknown) => Promise<T> } {
  async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = opts.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${opts.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 401) {
      opts.onUnauthorized?.();
      throw new ApiError(401, "AUTH_REQUIRED");
    }
    if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => ""));
    return (await res.json()) as T;
  }
  return {
    get: <T>(path: string): Promise<T> => request<T>("GET", path),
    post: <T>(path: string, body?: unknown): Promise<T> => request<T>("POST", path, body),
  };
}

export type RestClient = ReturnType<typeof createRestClient>;
```

删除 `web/src/api/client.ts` 与 `web/src/api/client.test.ts`（被 F1/F2 取代）。

- [ ] **Step 4: 运行测试确认通过**

Run: `npm test -- --run src/api`
Expected: PASS（8 用例：ws 6 + rest 3；jsdom 环境下 `WebSocket` stub 生效）

- [ ] **Step 5: 提交**

```bash
git add web/src/api/ws.ts web/src/api/rest.ts web/src/api/ws.test.ts web/src/api/rest.test.ts
git rm web/src/api/client.ts web/src/api/client.test.ts
git commit -m "feat(web): WS v2 传输层与 REST 客户端（替换旧 client）"
```

---

### Task 3: Zustand 五切片（含 seq 镜像核心）

**Files:**
- Create: `web/src/store/useBootstrapStore.ts`、`web/src/store/useAuthStore.ts`、`web/src/store/useSessionStore.ts`（重写）、`web/src/store/useOpsStore.ts`、`web/src/store/useUiStore.ts`
- Delete: 旧 `web/src/store/useSessionStore.ts`（被重写覆盖）、`web/src/store/useSessionStore.test.ts`
- Test: `web/src/store/useSessionStore.test.ts`（重写）、`web/src/store/useUiStore.test.ts`

**Interfaces:**
- Consumes: F1 的 `OutboundMessage`/`Question`/`BootstrapConfig`。
- Produces（供 F4-F7 消费）：
  - `useBootstrapStore`: `{bootstrap: BootstrapConfig | null, loaded: boolean, setLoaded(cfg), reset()}`
  - `useAuthStore`: `{token, account, status: "logged_out"|"verifying"|"logged_in", login(token, account), logout()}`
  - `useSessionStore`: `{sessionId, status, lastSeq, round, questions, questionExpiresAt, draftWo, confidenceScore, reviewRecord, riskFlag, hubAck, queuedLocal, manualReview, transcript, needsResume, setSessionId, setOnGap, applyMessage(msg), applySnapshot(state, seq), appendTranscript(line), reset()}`
  - `useOpsStore`: `{health, metrics, queueStats, lastFetched, setHealth, setMetrics, setQueueStats}`
  - `useUiStore`: `{view, theme, toasts, softBreak, connection, setView, toggleTheme, toast(msg), dismissToast(id), pushSoftBreak(p), clearSoftBreak(), setConnection(s)}`

- [ ] **Step 1: 写失败测试**

创建 `web/src/store/useSessionStore.test.ts`（重写，覆盖设计 3.3 镜像规则）：

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSessionStore } from "./useSessionStore";
import type { OutboundMessage } from "../schemas/ws";

function statusMsg(sessionId: string, seq: number, status: string): OutboundMessage {
  return { v: 2, type: "status", session_id: sessionId, seq, ts: "t", req_id: "", payload: { status } };
}
function snapshotMsg(sessionId: string, seq: number, state: Record<string, unknown>): OutboundMessage {
  return { v: 2, type: "session_snapshot", session_id: sessionId, seq, ts: "t", req_id: "", payload: { state, seq } };
}

beforeEach(() => useSessionStore.getState().reset());

describe("applyMessage 镜像规则（设计 3.3）", () => {
  it("seq 连续消息顺序应用并更新 lastSeq", () => {
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "PARSING"));
    useSessionStore.getState().applyMessage(statusMsg("s1", 2, "DELIVERED"));
    expect(useSessionStore.getState().status).toBe("DELIVERED");
    expect(useSessionStore.getState().lastSeq).toBe(2);
  });

  it("重复消息（seq <= lastSeq）被丢弃", () => {
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "PARSING"));
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "DELIVERED"));
    expect(useSessionStore.getState().status).toBe("PARSING");
  });

  it("seq 跳跃触发 gap → needsResume + onGap 回调", () => {
    const onGap = vi.fn();
    useSessionStore.getState().setOnGap(onGap);
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "PARSING"));
    useSessionStore.getState().applyMessage(statusMsg("s1", 3, "DELIVERED"));
    expect(useSessionStore.getState().needsResume).toBe(true);
    expect(onGap).toHaveBeenCalled();
  });

  it("session_snapshot 无条件重建镜像", () => {
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "PARSING"));
    const state = { session_id: "s1", status: "REVIEWING", draft_work_order: { wo_number: "WO-DRAFT-1" }, review_record: { review_score: 0.95 } };
    useSessionStore.getState().applyMessage(snapshotMsg("s1", 7, state));
    const s = useSessionStore.getState();
    expect(s.lastSeq).toBe(7);
    expect(s.status).toBe("REVIEWING");
    expect(s.draftWo).toEqual({ wo_number: "WO-DRAFT-1" });
    expect(s.reviewRecord).toEqual({ review_score: 0.95 });
    expect(s.questions).toEqual([]);
  });

  it("p0_interrogation 写入 questions/round/expiresAt", () => {
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "CLARIFYING"));
    const msg: OutboundMessage = { v: 2, type: "p0_interrogation", session_id: "s1", seq: 2, ts: "t", req_id: "", payload: { round: 1, questions: [{ qid: "q-1-action", field: "action", text: "您说的动作是？", type: "single_choice", options: ["审计", "修复"], required: true }], timeout_seconds: 300, expires_at: "2026-09-01T10:40:00" } };
    useSessionStore.getState().applyMessage(msg);
    expect(useSessionStore.getState().questions).toHaveLength(1);
    expect(useSessionStore.getState().round).toBe(1);
    expect(useSessionStore.getState().questionExpiresAt).toBe("2026-09-01T10:40:00");
  });

  it("wo_preview 写入草稿/置信度/风险标记；hub_ack 写入回执", () => {
    useSessionStore.getState().applyMessage({ v: 2, type: "wo_preview", session_id: "s1", seq: 1, ts: "t", req_id: "", payload: { draft_wo: { wo_number: "WO-DRAFT-1" }, confidence_score: 0.95, review_record: { review_score: 0.96 }, risk_flag: "", actions: ["confirm", "edit", "discard"] } });
    expect(useSessionStore.getState().draftWo).toEqual({ wo_number: "WO-DRAFT-1" });
    useSessionStore.getState().applyMessage({ v: 2, type: "hub_ack", session_id: "s1", seq: 2, ts: "t", req_id: "", payload: { ack: { wo_number: "WO-HAI-1" } } });
    expect(useSessionStore.getState().hubAck).toEqual({ wo_number: "WO-HAI-1" });
  });

  it("其他会话消息被忽略", () => {
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "PARSING"));
    useSessionStore.getState().applyMessage(statusMsg("other", 1, "DELIVERED"));
    expect(useSessionStore.getState().status).toBe("PARSING");
  });
});
```

创建 `web/src/store/useUiStore.test.ts`：

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "./useUiStore";

beforeEach(() => useUiStore.getState().reset());

describe("useUiStore", () => {
  it("主题切换 toggleTheme", () => {
    expect(useUiStore.getState().theme).toBe("light");
    useUiStore.getState().toggleTheme();
    expect(useUiStore.getState().theme).toBe("dark");
  });
  it("toast 追加与关闭", () => {
    useUiStore.getState().toast("hello");
    const id = useUiStore.getState().toasts[0].id;
    useUiStore.getState().dismissToast(id);
    expect(useUiStore.getState().toasts).toHaveLength(0);
  });
  it("软熔断 push 与清除", () => {
    useUiStore.getState().pushSoftBreak({ usage_percent: 6.0, monthly_quota_tokens: 1000000 });
    expect(useUiStore.getState().softBreak).not.toBeNull();
    useUiStore.getState().clearSoftBreak();
    expect(useUiStore.getState().softBreak).toBeNull();
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/store`
Expected: FAIL，`Cannot find module './useSessionStore'` 等

- [ ] **Step 3: 实现五个 store**

创建 `web/src/store/useSessionStore.ts`（重写）：

```ts
import { create } from "zustand";
import type { OutboundMessage, Question, ReviewRecord } from "../schemas/ws";

interface QueuedLocal { woNumber: string; nextRetryAt: string }
interface ManualReview { draftWo: Record<string, unknown>; reason: string }

export interface SessionSlice {
  sessionId: string;
  status: string;
  lastSeq: number;
  round: number;
  questions: Question[];
  questionExpiresAt: string;
  draftWo: Record<string, unknown> | null;
  confidenceScore: number;
  reviewRecord: ReviewRecord | null;
  riskFlag: string;
  hubAck: Record<string, unknown> | null;
  queuedLocal: QueuedLocal | null;
  manualReview: ManualReview | null;
  transcript: string[];
  needsResume: boolean;
  setSessionId: (id: string) => void;
  setOnGap: (fn: (() => void) | null) => void;
  applyMessage: (msg: OutboundMessage) => void;
  applySnapshot: (state: Record<string, unknown>, seq: number) => void;
  appendTranscript: (line: string) => void;
  reset: () => void;
}

export const useSessionStore = create<SessionSlice>((set, get) => ({
  sessionId: "", status: "IDLE", lastSeq: 0, round: 0, questions: [], questionExpiresAt: "",
  draftWo: null, confidenceScore: 0, reviewRecord: null, riskFlag: "", hubAck: null,
  queuedLocal: null, manualReview: null, transcript: [], needsResume: false,
  onGapRef: null,

  setSessionId: (id: string): void => set({ sessionId: id, status: "IDLE", lastSeq: 0 }),
  setOnGap: (fn: (() => void) | null): void => set({ onGapRef: fn }),

  applyMessage: (msg: OutboundMessage): void => {
    const s = get();
    if (!msg.session_id) return;
    if (s.sessionId && msg.session_id !== s.sessionId) return;
    if (msg.seq <= s.lastSeq) return;
    if (msg.seq > s.lastSeq + 1) {
      set({ needsResume: true });
      s.onGapRef?.();
      return;
    }
    const patch: Partial<SessionSlice> = { lastSeq: msg.seq, needsResume: false };
    switch (msg.type) {
      case "status":
        patch.status = msg.payload.status;
        if (msg.payload.status === "DELIVERED" || msg.payload.status === "MANUAL_REVIEW" || msg.payload.status === "QUEUED_LOCAL" || msg.payload.status === "ABANDONED" || msg.payload.status === "FAILED") {
          patch.questions = [];
          patch.questionExpiresAt = "";
        }
        break;
      case "session_snapshot":
        get().applySnapshot(msg.payload.state, msg.payload.seq);
        return;
      case "p0_interrogation":
        patch.questions = msg.payload.questions;
        patch.round = msg.payload.round;
        patch.questionExpiresAt = msg.payload.expires_at;
        patch.draftWo = null;
        break;
      case "p0_timeout":
        patch.transcript = [...s.transcript, `P0 第 ${msg.payload.round} 轮超时`];
        break;
      case "wo_preview":
        patch.draftWo = msg.payload.draft_wo;
        patch.confidenceScore = msg.payload.confidence_score;
        patch.reviewRecord = msg.payload.review_record ?? null;
        patch.riskFlag = msg.payload.risk_flag;
        patch.questions = [];
        patch.hubAck = null;
        patch.queuedLocal = null;
        patch.manualReview = null;
        break;
      case "review_result":
        patch.reviewRecord = msg.payload.review_record;
        break;
      case "hub_ack":
        patch.hubAck = msg.payload.ack;
        patch.status = "DELIVERED";
        break;
      case "queued_local":
        patch.queuedLocal = { woNumber: msg.payload.wo_number, nextRetryAt: msg.payload.next_retry_at };
        patch.status = "QUEUED_LOCAL";
        break;
      case "manual_review":
        patch.manualReview = { draftWo: msg.payload.draft_wo, reason: msg.payload.reason };
        patch.status = "MANUAL_REVIEW";
        break;
      default:
        break;
    }
    set(patch);
  },

  applySnapshot: (state: Record<string, unknown>, seq: number): void => {
    set({
      sessionId: String(state.session_id ?? ""),
      status: String(state.status ?? "UNKNOWN"),
      lastSeq: seq,
      questions: [],
      questionExpiresAt: "",
      round: 0,
      draftWo: (state.draft_work_order as Record<string, unknown> | undefined) ?? null,
      confidenceScore: Number((state.draft_work_order as Record<string, unknown> | undefined)?.confidence_score ?? 0),
      reviewRecord: (state.review_record as ReviewRecord | undefined) ?? null,
      riskFlag: String((state.draft_work_order as Record<string, unknown> | undefined)?.risk_flag ?? ""),
      hubAck: (state.hub_ack as Record<string, unknown> | undefined) ?? null,
      queuedLocal: null,
      manualReview: null,
      transcript: [],
      needsResume: false,
    });
  },

  appendTranscript: (line: string): void => set((st) => ({ transcript: [...st.transcript, line] })),
  reset: (): void => set({
    sessionId: "", status: "IDLE", lastSeq: 0, round: 0, questions: [], questionExpiresAt: "",
    draftWo: null, confidenceScore: 0, reviewRecord: null, riskFlag: "", hubAck: null,
    queuedLocal: null, manualReview: null, transcript: [], needsResume: false,
  }),
}));
```

注意：`onGapRef` 字段未列入接口（内部实现），需在 `SessionSlice` 中声明为 `onGapRef?: (() => void) | null`——见下修正（Step 4 说明）：在接口中加 `onGapRef: (() => void) | null;` 与初始值 `null`。

创建其余四个 store：

```ts
// web/src/store/useBootstrapStore.ts
import { create } from "zustand";
import type { BootstrapConfig } from "../schemas/ws";

export interface BootstrapSlice {
  bootstrap: BootstrapConfig | null;
  loaded: boolean;
  setLoaded: (cfg: BootstrapConfig) => void;
  reset: () => void;
}

export const useBootstrapStore = create<BootstrapSlice>((set) => ({
  bootstrap: null,
  loaded: false,
  setLoaded: (cfg: BootstrapConfig): void => set({ bootstrap: cfg, loaded: true }),
  reset: (): void => set({ bootstrap: null, loaded: false }),
}));
```

```ts
// web/src/store/useAuthStore.ts
import { create } from "zustand";

export type AuthStatus = "logged_out" | "verifying" | "logged_in";

export interface AuthSlice {
  token: string;
  account: string;
  status: AuthStatus;
  login: (token: string, account: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthSlice>((set) => ({
  token: "", account: "", status: "logged_out",
  login: (token: string, account: string): void => set({ token, account, status: "logged_in" }),
  logout: (): void => set({ token: "", account: "", status: "logged_out" }),
}));
```

```ts
// web/src/store/useOpsStore.ts
import { create } from "zustand";

export interface OpsSlice {
  health: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  queueStats: Record<string, number> | null;
  lastFetched: string;
  setHealth: (v: Record<string, unknown>) => void;
  setMetrics: (v: Record<string, unknown>) => void;
  setQueueStats: (v: Record<string, number>) => void;
}

export const useOpsStore = create<OpsSlice>((set) => ({
  health: null, metrics: null, queueStats: null, lastFetched: "",
  setHealth: (v: Record<string, unknown>): void => set({ health: v, lastFetched: new Date().toISOString() }),
  setMetrics: (v: Record<string, unknown>): void => set({ metrics: v, lastFetched: new Date().toISOString() }),
  setQueueStats: (v: Record<string, number>): void => set({ queueStats: v, lastFetched: new Date().toISOString() }),
}));
```

```ts
// web/src/store/useUiStore.ts
import { create } from "zustand";
import type { IntakeSocket } from "../api/ws";

export type View = "login" | "intake" | "expert" | "sessions" | "ops";
export type Theme = "light" | "dark";
export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export interface Toast { id: number; text: string }
export interface SoftBreak { usagePercent: number; monthlyQuotaTokens: number }

export interface UiSlice {
  view: View;
  theme: Theme;
  toasts: Toast[];
  softBreak: SoftBreak | null;
  connection: ConnectionState;
  socket: IntakeSocket | null;   // hook 创建的实时连接，页面经此发送（自审修正）
  setView: (v: View) => void;
  toggleTheme: () => void;
  toast: (text: string) => void;
  dismissToast: (id: number) => void;
  pushSoftBreak: (p: SoftBreak) => void;
  clearSoftBreak: () => void;
  setConnection: (s: ConnectionState) => void;
  setSocket: (s: IntakeSocket | null) => void;
  reset: () => void;
}

let toastId = 0;

export const useUiStore = create<UiSlice>((set) => ({
  view: "login", theme: "light", toasts: [], softBreak: null, connection: "closed", socket: null,
  setView: (v: View): void => set({ view: v }),
  toggleTheme: (): void => set((s) => ({ theme: s.theme === "light" ? "dark" : "light" })),
  toast: (text: string): void => set((s) => ({ toasts: [...s.toasts, { id: ++toastId, text }] })),
  dismissToast: (id: number): void => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  pushSoftBreak: (p: SoftBreak): void => set({ softBreak: p }),
  clearSoftBreak: (): void => set({ softBreak: null }),
  setConnection: (s: ConnectionState): void => set({ connection: s }),
  setSocket: (s: IntakeSocket | null): void => set({ socket: s }),
  reset: (): void => set({ view: "login", theme: "light", toasts: [], softBreak: null, connection: "closed", socket: null }),
}));
```

- [ ] **Step 4: 修正接口并跑测试**

在 `useSessionStore.ts` 的 `SessionSlice` 接口中追加：

```ts
  onGapRef: (() => void) | null;
```

并在初始值中加 `onGapRef: null`（`setOnGap` 已引用）。同时更新 `reset()` 恢复 `onGapRef: null`。

Run: `npm test -- --run src/store`
Expected: PASS（9 用例）

- [ ] **Step 5: 全量前端回归 + 提交**

Run: `npm test -- --run`
Expected: PASS（schemas 3 + api 8 + store 9；旧 client/store 测试已删除）

```bash
git rm web/src/store/useSessionStore.test.ts 2>/dev/null || true
git add web/src/store/ web/src/schemas/ws.contract.test.ts web/src/api/
git commit -m "feat(web): Zustand 五切片与 seq 镜像规则"
```

---

### Task 4: 设计系统 tokens 与 AppShell

**Files:**
- Create: `web/src/styles/tokens.css`
- Create: `web/src/hooks/useIntakeSocket.ts`
- Rewrite: `web/src/App.tsx`
- Test: `web/src/App.test.tsx`

**Interfaces:**
- Consumes: F3 全部 store；F2 `IntakeSocket`；F1 类型。
- Produces: `AppShell`（默认导出），`useIntakeSocket()` hook（连接编排 + 消息路由 + auth 首消息）。

- [ ] **Step 1: 写失败测试**

创建 `web/src/App.test.tsx`：

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { App } from "./App";
import { useAuthStore } from "./store/useAuthStore";
import { useUiStore } from "./store/useUiStore";

// 简化：不依赖 @testing-library 时可用 react-dom/test-utils renderIntoDocument 替代；
// 本测试用 @testing-library/react（需先安装：npm i -D @testing-library/react）
vi.mock("./api/ws", () => ({ IntakeSocket: class { connect = vi.fn(); close = vi.fn(); send = vi.fn(); } }));

beforeEach(() => {
  useAuthStore.getState().logout();
  useUiStore.getState().reset();
});

describe("AppShell", () => {
  it("未登录时渲染登录页", () => {
    render(<App />);
    expect(screen.getByText("AKO 工厂大门")).toBeDefined();
    expect(screen.getByPlaceholderText("账号")).toBeDefined();
  });
  it("登录后导航可切换视图", () => {
    act(() => useAuthStore.getState().login("dev-token", "admin"));
    act(() => useUiStore.getState().setView("ops"));
    render(<App />);
    expect(screen.getByText("运维面板")).toBeDefined();
  });
});
```

（若 `@testing-library/react` 与 jsdom 版本冲突，改用 `react-dom/client` + 原生 DOM 断言——以实际运行为准并记录。）

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/App.test.tsx`
Expected: FAIL（缺 App 导出/组件）

- [ ] **Step 3: 先建页面占位 stub（预检裁定：F4 渲染 F5-F7 才实现的页面，先以命名 stub 跑通 AppShell）**

创建 5 个占位文件（F5-F7 完整替换，占位渲染自身名称）：

```tsx
// web/src/pages/LoginPage.tsx（占位，F5 完整替换）
export function LoginPage(): JSX.Element { return <div>登录</div>; }
// web/src/pages/IntakePage.tsx（占位，F6 完整替换）
export function IntakePage(): JSX.Element { return <div>IntakePage</div>; }
// web/src/pages/ExpertPage.tsx（占位，F7 完整替换）
export function ExpertPage(): JSX.Element { return <div>ExpertPage</div>; }
// web/src/pages/SessionsPage.tsx（占位，F7 完整替换）
export function SessionsPage(): JSX.Element { return <div>SessionsPage</div>; }
// web/src/pages/OpsPage.tsx（占位，F7 完整替换）
export function OpsPage(): JSX.Element { return <div>运维面板</div>; }
```

同步调整 F4 Step 1 的 App.test 断言（stub 语义）：`getByPlaceholderText("账号")` 改为 `getByText("登录")`；`getByText("运维面板")` 保持（stub 渲染该文本）。F5/F7 各自的页面测试断言真实内容。

- [ ] **Step 4: 实现 tokens.css、useIntakeSocket、AppShell**

创建 `web/src/styles/tokens.css`：

```css
:root {
  --c-gold-grad: linear-gradient(90deg, #8a6d3b, #c9a227);
  --c-gold: #c9a227;
  --c-gold-dark: #8a6d3b;
  --c-bg: #faf6ef;
  --c-text: #3d2b1f;
  --c-border: #e5dcc8;
  --c-card: #ffffff;
  --c-success: #3e7d4f;
  --c-warning: #b8860b;
  --c-danger: #a33a2b;
  --c-review: #d97706;
  --c-info: #4a6fa5;
  --radius: 8px;
  --gap: 8px;
}
html[data-theme="dark"] {
  --c-bg: #1d1812;
  --c-text: #ece3d2;
  --c-border: #4a3f2e;
  --c-card: #2a231a;
  --c-gold: #d4af37;
}
body { margin: 0; font-family: system-ui, sans-serif; background: var(--c-bg); color: var(--c-text); }
```

创建 `web/src/hooks/useIntakeSocket.ts`：

```ts
import { useEffect, useRef } from "react";
import { IntakeSocket } from "../api/ws";
import { useAuthStore } from "../store/useAuthStore";
import { useBootstrapStore } from "../store/useBootstrapStore";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

const WS_URL: string = (import.meta.env.VITE_INTAKE_WS_URL as string | undefined) ?? `${location.origin.replace(/^http/, "ws")}/ws/intake`;

export function useIntakeSocket(): void {
  const token = useAuthStore((s) => s.token);
  const socketRef = useRef<IntakeSocket | null>(null);

  useEffect(() => {
    const socket = new IntakeSocket({
      url: WS_URL,
      onOpen: (): void => {
        const t = useAuthStore.getState().token;
        if (t) socket.send("auth", "", { token: t });
      },
      onMessage: (msg): void => {
        if (msg.type === "hello") {
          useBootstrapStore.getState().setLoaded(msg.payload.bootstrap);
        } else if (msg.type === "soft_break") {
          useUiStore.getState().pushSoftBreak(msg.payload);
        } else if (msg.type === "error") {
          useUiStore.getState().toast(`错误 ${msg.payload.code}: ${msg.payload.message}`);
        } else {
          useSessionStore.getState().applyMessage(msg);
        }
      },
      onStateChange: (s): void => useUiStore.getState().setConnection(s),
    });
    socketRef.current = socket;
    useUiStore.getState().setSocket(socket); // 页面经 uiStore.socket 发送（自审修正）
    socket.connect();
    return () => {
      socket.close();
      socketRef.current = null;
      useUiStore.getState().setSocket(null);
    };
  }, [token]);
}
```

重写 `web/src/App.tsx`：

```tsx
import { useEffect } from "react";
import { LoginPage } from "./pages/LoginPage";
import { IntakePage } from "./pages/IntakePage";
import { ExpertPage } from "./pages/ExpertPage";
import { SessionsPage } from "./pages/SessionsPage";
import { OpsPage } from "./pages/OpsPage";
import { useIntakeSocket } from "./hooks/useIntakeSocket";
import { useAuthStore } from "./store/useAuthStore";
import { useUiStore, type View } from "./store/useUiStore";
import "./styles/tokens.css";

const NAV: { view: View; label: string }[] = [
  { view: "intake", label: "自然语言入口" },
  { view: "expert", label: "专家模式" },
  { view: "sessions", label: "会话续传" },
  { view: "ops", label: "运维面板" },
];

export function App(): JSX.Element {
  useIntakeSocket();
  const loggedIn = useAuthStore((s) => s.status === "logged_in");
  const view = useUiStore((s) => s.view);
  const theme = useUiStore((s) => s.theme);
  const connection = useUiStore((s) => s.connection);
  const softBreak = useUiStore((s) => s.softBreak);
  const setView = useUiStore((s) => s.setView);
  const toggleTheme = useUiStore((s) => s.toggleTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  if (!loggedIn) return <LoginPage />;

  return (
    <div style={{ minHeight: "100vh", background: "var(--c-bg)", color: "var(--c-text)" }}>
      <header style={{ padding: "16px 24px", background: "var(--c-gold-grad)", color: "#fff" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h1 style={{ margin: 0, fontSize: 20 }}>AKO 工厂大门</h1>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span title="连接状态" style={{ width: 10, height: 10, borderRadius: 5, background: connection === "open" ? "#3e7d4f" : connection === "reconnecting" ? "#b8860b" : "#a33a2b" }} />
            <button onClick={toggleTheme}>{theme === "light" ? "深色" : "浅色"}</button>
            <button onClick={() => useAuthStore.getState().logout()}>登出</button>
          </div>
        </div>
        <nav style={{ marginTop: 8, display: "flex", gap: 12 }}>
          {NAV.map((n) => (
            <button key={n.view} onClick={() => setView(n.view)} style={{ fontWeight: view === n.view ? 700 : 400 }}>{n.label}</button>
          ))}
        </nav>
      </header>
      {softBreak && (
        <div style={{ background: "var(--c-warning)", color: "#fff", padding: "8px 24px" }}>
          预算软熔断：用量 {softBreak.usagePercent.toFixed(1)}% / 月配额 {softBreak.monthlyQuotaTokens.toLocaleString()} tokens，已强制专家模式
        </div>
      )}
      {/* 软熔断强制专家模式（设计 4.3/7.6）：仅当用户停在自然语言入口时切换 */}
      <ForceExpertOnSoftBreak active={Boolean(softBreak)} />
      <main style={{ padding: 24, maxWidth: 760, margin: "0 auto" }}>
        {view === "intake" && <IntakePage />}
        {view === "expert" && <ExpertPage />}
        {view === "sessions" && <SessionsPage />}
        {view === "ops" && <OpsPage />}
      </main>
    </div>
  );
}

function ForceExpertOnSoftBreak({ active }: { active: boolean }): null {
  useEffect(() => {
    if (active && useUiStore.getState().view === "intake") {
      useUiStore.getState().setView("expert");
    }
  }, [active]);
  return null;
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `npm test -- --run src/App.test.tsx`
Expected: PASS（stub 页面已就位；F5-F7 将完整替换）

- [ ] **Step 6: 提交**

```bash
git add web/src/styles/tokens.css web/src/hooks/useIntakeSocket.ts web/src/App.tsx web/src/App.test.tsx web/src/pages/LoginPage.tsx web/src/pages/IntakePage.tsx web/src/pages/ExpertPage.tsx web/src/pages/SessionsPage.tsx web/src/pages/OpsPage.tsx
git commit -m "feat(web): 设计系统 tokens、AppShell 与 socket 编排 hook（含页面占位）"
```

---

### Task 5: LoginPage 与 bootstrap/auth 接线

**Files:**
- Create: `web/src/pages/LoginPage.tsx`、`web/src/pages/LoginPage.test.tsx`

**Interfaces:**
- Consumes: F2 `createRestClient`、F3 `useAuthStore`/`useBootstrapStore`/`useUiStore`。
- Produces: `LoginPage`（默认导出）。

- [ ] **Step 1: 写失败测试**

创建 `web/src/pages/LoginPage.test.tsx`：

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LoginPage } from "./LoginPage";
import { useAuthStore } from "../store/useAuthStore";

vi.mock("../api/rest", () => ({
  createRestClient: () => ({
    post: vi.fn(async (path: string) => {
      if (path === "/api/v1/identity/login") return { token: "tok-1", expires_at: "", identity: { account: "a" } };
      throw new Error("unexpected");
    }),
    get: vi.fn(async () => ({})),
  }),
}));

beforeEach(() => useAuthStore.getState().logout());

describe("LoginPage", () => {
  it("账号+六位指纹校验：不足 6 位提示", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByPlaceholderText("账号"), { target: { value: "admin" } });
    fireEvent.change(screen.getByPlaceholderText("六位指纹"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(screen.getByText(/六位数字/)).toBeDefined());
  });
  it("登录成功写入 auth store", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByPlaceholderText("账号"), { target: { value: "admin" } });
    fireEvent.change(screen.getByPlaceholderText("六位指纹"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(useAuthStore.getState().status).toBe("logged_in"));
    expect(useAuthStore.getState().token).toBe("tok-1");
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/pages/LoginPage.test.tsx`
Expected: FAIL，`Cannot find module './LoginPage'`

- [ ] **Step 3: 实现 LoginPage**

创建 `web/src/pages/LoginPage.tsx`：

```tsx
import { useState } from "react";
import { createRestClient } from "../api/rest";
import { useAuthStore } from "../store/useAuthStore";
import { useUiStore } from "../store/useUiStore";

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

interface LoginResult { token: string; expires_at: string; identity: { account: string } }

export function LoginPage(): JSX.Element {
  const [account, setAccount] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const login = useAuthStore((s) => s.login);

  async function submit(): Promise<void> {
    if (!/^\d{6}$/.test(fingerprint)) { setError("指纹须为六位数字"); return; }
    setBusy(true);
    setError("");
    try {
      const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => "", onUnauthorized: () => setError("身份校验失败") });
      const res = await rest.post<LoginResult>("/api/v1/identity/login", { account, fingerprint });
      login(res.token, res.identity.account);
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ maxWidth: 360, margin: "80px auto", textAlign: "center" }}>
      <h1 style={{ background: "var(--c-gold-grad)", WebkitBackgroundClip: "text", color: "transparent" }}>AKO 工厂大门</h1>
      <p>登录 AKO 体系（账号 + 六位指纹）</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input placeholder="账号" value={account} onChange={(e) => setAccount(e.target.value)} style={{ padding: 8 }} />
        <input placeholder="六位指纹" inputMode="numeric" maxLength={6} value={fingerprint} onChange={(e) => setFingerprint(e.target.value.replace(/\D/g, ""))} style={{ padding: 8 }} />
        <button onClick={() => void submit()} disabled={busy || !account}>{busy ? "登录中…" : "登录"}</button>
        {error && <p style={{ color: "var(--c-danger)" }}>{error}</p>}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npm test -- --run src/pages/LoginPage.test.tsx`
Expected: PASS（2 用例）

- [ ] **Step 5: 提交**

```bash
git add web/src/pages/LoginPage.tsx web/src/pages/LoginPage.test.tsx
git commit -m "feat(web): 登录页与身份门禁接线"
```

---

### Task 6: IntakePage 全流程（输入→澄清→预览→评审→投递）

**Files:**
- Rewrite: `web/src/pages/IntakePage.tsx`
- Create: `web/src/components/InputComposer.tsx`、`web/src/components/ProgressStepper.tsx`、`web/src/components/QuestionCard.tsx`（升级）、`web/src/components/WoPreviewCard.tsx`（升级）、`web/src/components/ReviewPanel.tsx`、`web/src/components/DeliveryResultCard.tsx`、`web/src/components/TranscriptPanel.tsx`
- Test: `web/src/pages/IntakePage.test.tsx`、`web/src/components/QuestionCard.test.tsx`

**Interfaces:**
- Consumes: F2 `IntakeSocket`（经 hook 或注入）、F3 sessionStore/uiStore、F1 类型。
- Produces: 各组件默认导出；`IntakePage` 默认导出（接收可选 `socket: { send: (type, sessionId, payload?) => boolean } | null` 注入，便于测试）。

- [ ] **Step 1: 写失败测试**

创建 `web/src/components/QuestionCard.test.tsx`：

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QuestionCard } from "./QuestionCard";
import type { Question } from "../schemas/ws";

const QUESTIONS: Question[] = [
  { qid: "q-1-action", field: "action", text: "您说的动作是？", type: "single_choice", options: ["审计", "修复"], required: true },
  { qid: "q-1-scope", field: "scope", text: "请明确范围", type: "open", options: [], required: true },
];

beforeEach(() => vi.restoreAllMocks());

describe("QuestionCard", () => {
  it("渲染单选与填空两种形态", () => {
    render(<QuestionCard questions={QUESTIONS} onAnswer={vi.fn()} onConservative={vi.fn()} />);
    expect(screen.getByText("您说的动作是？")).toBeDefined();
    expect(screen.getByText("请明确范围")).toBeDefined();
  });
  it("必答校验：未填全时提交不回调", () => {
    const onAnswer = vi.fn();
    render(<QuestionCard questions={QUESTIONS} onAnswer={onAnswer} onConservative={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "提交答复" }));
    expect(onAnswer).not.toHaveBeenCalled();
  });
  it("填全后提交回调 answers", () => {
    const onAnswer = vi.fn();
    render(<QuestionCard questions={QUESTIONS} onAnswer={onAnswer} onConservative={vi.fn()} />);
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "审计" } });
    fireEvent.change(screen.getByPlaceholderText("请填写"), { target: { value: "全局审计" } });
    fireEvent.click(screen.getByRole("button", { name: "提交答复" }));
    expect(onAnswer).toHaveBeenCalledWith([
      { qid: "q-1-action", value: "审计" },
      { qid: "q-1-scope", value: "全局审计" },
    ]);
  });
  it("点击保守策略按钮回调 onConservative", () => {
    const onConservative = vi.fn();
    render(<QuestionCard questions={QUESTIONS} onAnswer={vi.fn()} onConservative={onConservative} />);
    fireEvent.click(screen.getByRole("button", { name: "按最保守策略处理" }));
    expect(onConservative).toHaveBeenCalled();
  });
});
```

创建 `web/src/pages/IntakePage.test.tsx`：

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { IntakePage } from "./IntakePage";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

function makeSocket() {
  const sent: { type: string; sessionId: string; payload: Record<string, unknown> }[] = [];
  const socket = { send: (type: string, sessionId: string, payload: Record<string, unknown> = {}) => { sent.push({ type, sessionId, payload }); return true; } };
  return { socket, sent };
}

beforeEach(() => { useSessionStore.getState().reset(); useUiStore.getState().reset(); });

describe("IntakePage", () => {
  it("提交输入发送 intake_input 并生成会话号", async () => {
    const { socket, sent } = makeSocket();
    render(<IntakePage socket={socket} />);
    fireEvent.change(screen.getByPlaceholderText(/描述你的需求/), { target: { value: "修复报价模块的bug，只动校验逻辑，不动数据库" } });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].type).toBe("intake_input");
    expect(sent[0].payload.text.length).toBeGreaterThanOrEqual(10);
  });
  it("短文本（<10 字符）不发送并提示", () => {
    const { socket, sent } = makeSocket();
    render(<IntakePage socket={socket} />);
    fireEvent.change(screen.getByPlaceholderText(/描述你的需求/), { target: { value: "太短" } });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
    expect(sent).toHaveLength(0);
    expect(screen.getByText(/10~2000/)).toBeDefined();
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/pages/IntakePage.test.tsx src/components/QuestionCard.test.tsx`
Expected: FAIL，`Cannot find module`

- [ ] **Step 3: 实现组件与 IntakePage**

创建 `web/src/components/InputComposer.tsx`：

```tsx
import { useState } from "react";

interface Props { onSubmit: (text: string) => void }

const MIN_LEN = 10;
const MAX_LEN = 2000;

export function InputComposer({ onSubmit }: Props): JSX.Element {
  const [text, setText] = useState("");
  const tooShort = text.length > 0 && text.length < MIN_LEN;
  return (
    <div>
      <textarea
        rows={4} style={{ width: "100%", fontFamily: "inherit" }}
        placeholder="描述你的需求，例如：帮我看看报价模块最近的数据有没有问题"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
        <span style={{ color: tooShort ? "var(--c-danger)" : "var(--c-text)", fontSize: 12 }}>
          {text.length}/{MAX_LEN}（须 10~2000 字符）
        </span>
        <button
          disabled={text.length < MIN_LEN || text.length > MAX_LEN}
          onClick={() => { onSubmit(text.trim()); setText(""); }}
        >
          提交
        </button>
      </div>
      {tooShort && <p style={{ color: "var(--c-danger)", fontSize: 12 }}>文本须 10~2000 字符</p>}
    </div>
  );
}
```

创建 `web/src/components/ProgressStepper.tsx`：

```tsx
const STEPS = ["PARSING", "AMBIGUITY_DETECTED", "CLARIFYING", "FORM_BUILDING", "VALIDATING", "REVIEWING", "TERMINAL"] as const;
const TERMINAL = ["DELIVERED", "QUEUED_LOCAL", "MANUAL_REVIEW", "FAILED", "ABANDONED"] as const;

function indexOf(status: string): number {
  if (TERMINAL.includes(status as (typeof TERMINAL)[number])) return STEPS.length - 1;
  const i = STEPS.indexOf(status as (typeof STEPS)[number]);
  return i === -1 ? 0 : i;
}

export function ProgressStepper({ status }: { status: string }): JSX.Element | null {
  const idx = indexOf(status);
  if (status === "IDLE") return null;
  return (
    <ol style={{ display: "flex", gap: 4, listStyle: "none", padding: 0, margin: "12px 0" }}>
      {STEPS.map((s, i) => (
        <li key={s} style={{ flex: 1, height: 6, borderRadius: 3, background: i <= idx ? "var(--c-gold)" : "var(--c-border)" }} title={s} />
      ))}
    </ol>
  );
}
```

升级 `web/src/components/QuestionCard.tsx`：

```tsx
import { useState } from "react";
import type { Question } from "../schemas/ws";

interface Props {
  questions: Question[];
  onAnswer: (answers: { qid: string; value: string }[]) => void;
  onConservative: () => void;
}

export function QuestionCard({ questions, onAnswer, onConservative }: Props): JSX.Element {
  const [values, setValues] = useState<Record<string, string>>({});
  const allFilled = questions.every((q) => (values[q.qid] ?? "").trim().length > 0);
  const submit = (): void => {
    if (!allFilled) return;
    onAnswer(questions.map((q) => ({ qid: q.qid, value: values[q.qid] ?? "" })));
  };
  return (
    <div style={{ border: "1px solid var(--c-gold)", borderRadius: "var(--radius)", padding: 12, background: "var(--c-card)" }}>
      <h3 style={{ marginTop: 0 }}>P0 歧义澄清</h3>
      {questions.map((q) => (
        <div key={q.qid} style={{ margin: "8px 0" }}>
          <p style={{ margin: "4px 0" }}>{q.text}{q.required ? " *" : ""}</p>
          {q.type === "single_choice" ? (
            <select value={values[q.qid] ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, [q.qid]: e.target.value }))}>
              <option value="">请选择</option>
              {q.options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
            </select>
          ) : (
            <input placeholder="请填写" value={values[q.qid] ?? ""} onChange={(e) => setValues((prev) => ({ ...prev, [q.qid]: e.target.value }))} style={{ width: "100%" }} />
          )}
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
        <button onClick={onConservative}>按最保守策略处理</button>
        <button onClick={submit} disabled={!allFilled}>提交答复</button>
      </div>
    </div>
  );
}
```

升级 `web/src/components/WoPreviewCard.tsx`：

```tsx
import { useState } from "react";

interface Props {
  wo: Record<string, unknown>;
  confidenceScore: number;
  reviewScore?: number | null;
  riskFlag?: string;
  onEdit: (draft: Record<string, unknown>) => void;
  onConfirm: () => void;
  onDiscard: () => void;
}

const FIELDS: { key: string; label: string }[] = [
  { key: "module", label: "模块" }, { key: "action", label: "动作" }, { key: "scope", label: "范围" },
  { key: "rules", label: "铁律" }, { key: "prohibitions", label: "禁止" },
  { key: "deliverable", label: "交付" }, { key: "deadline", label: "时限" },
];

export function WoPreviewCard({ wo, confidenceScore, reviewScore, riskFlag, onEdit, onConfirm, onDiscard }: Props): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>(wo);
  const [piiMasked] = useState(true); // 后端出站已 mask_pii（设计 3.6 第三重），徽章仅展示

  const save = (): void => { onEdit(draft); setEditing(false); };

  return (
    <div style={{ border: "1px solid var(--c-gold)", borderRadius: "var(--radius)", padding: 12, background: "var(--c-card)" }}>
      <h3 style={{ marginTop: 0 }}>
        工单预览
        {piiMasked && <span style={{ fontSize: 11, marginLeft: 8, color: "var(--c-info)" }}>PII 已脱敏</span>}
        {riskFlag && <span style={{ fontSize: 11, marginLeft: 8, color: "var(--c-danger)" }}>{riskFlag}</span>}
      </h3>
      <p style={{ fontSize: 13 }}>置信度 {Math.round(confidenceScore * 100)}%{reviewScore !== undefined && reviewScore !== null ? ` · 评审分 ${reviewScore.toFixed(2)}` : ""} · 编号 {String(wo.wo_number ?? "—")}</p>
      {FIELDS.map((f) => (
        <div key={f.key} style={{ margin: "6px 0" }}>
          <strong style={{ fontSize: 13 }}>{f.label}：</strong>
          {editing ? (
            <input value={String(draft[f.key] ?? "")} onChange={(e) => setDraft((prev) => ({ ...prev, [f.key]: e.target.value }))} style={{ width: "100%" }} />
          ) : (
            <span style={{ fontSize: 13 }}>{formatValue(wo[f.key])}</span>
          )}
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 8 }}>
        {editing ? (
          <>
            <button onClick={() => { setDraft(wo); setEditing(false); }}>取消</button>
            <button onClick={save}>保存修改</button>
          </>
        ) : (
          <>
            <button onClick={() => setEditing(true)}>编辑</button>
            <button onClick={onDiscard}>放弃</button>
            <button onClick={onConfirm} style={{ background: "var(--c-gold-grad)", color: "#fff" }}>确认投递</button>
          </>
        )}
      </div>
    </div>
  );
}

function formatValue(v: unknown): string {
  if (Array.isArray(v)) return v.join("；");
  if (v === null || v === undefined) return "";
  return String(v);
}
```

创建 `web/src/components/ReviewPanel.tsx`：

```tsx
import type { ReviewRecord } from "../schemas/ws";

interface Props {
  review: ReviewRecord;
  threshold: number;
  onConfirmHuman: () => void;
  onConfirmed: boolean;
}

export function ReviewPanel({ review, threshold, onConfirmHuman, onConfirmed }: Props): JSX.Element | null {
  if (review.review_score >= threshold) return null;
  return (
    <div style={{ border: "1px solid var(--c-review)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
      <h3 style={{ marginTop: 0, color: "var(--c-review)" }}>需人工确认（评审分 {review.review_score.toFixed(2)} &lt; {threshold}）</h3>
      {review.differences.length > 0 && (
        <ul style={{ fontSize: 13 }}>{review.differences.map((d, i) => <li key={i}>{d}</li>)}</ul>
      )}
      {onConfirmed ? <p style={{ fontSize: 13, color: "var(--c-success)" }}>已确认，请继续投递。</p> : (
        <button onClick={onConfirmHuman}>人工确认通过</button>
      )}
    </div>
  );
}
```

创建 `web/src/components/DeliveryResultCard.tsx`：

```tsx
interface Props {
  hubAck: Record<string, unknown> | null;
  queuedLocal: { woNumber: string; nextRetryAt: string } | null;
  manualReview: { draftWo: Record<string, unknown>; reason: string } | null;
}

export function DeliveryResultCard({ hubAck, queuedLocal, manualReview }: Props): JSX.Element | null {
  if (hubAck) {
    return (
      <div style={{ border: "1px solid var(--c-success)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
        <h3 style={{ marginTop: 0, color: "var(--c-success)" }}>已投递 Hub</h3>
        <p style={{ fontSize: 13 }}>正式编号：{String(hubAck.wo_number ?? "—")} · 队列位置：{String(hubAck.queue_position ?? "—")} · 追踪号：{String(hubAck.hub_trace_id ?? "—")}</p>
      </div>
    );
  }
  if (queuedLocal) {
    return (
      <div style={{ border: "1px solid var(--c-warning)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
        <h3 style={{ marginTop: 0, color: "var(--c-warning)" }}>Hub 不可达，已入本地队列（零丢失）</h3>
        <p style={{ fontSize: 13 }}>工单 {queuedLocal.woNumber} · 下次重试 {queuedLocal.nextRetryAt || "按退避策略"}</p>
      </div>
    );
  }
  if (manualReview) {
    return (
      <div style={{ border: "1px solid var(--c-review)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
        <h3 style={{ marginTop: 0, color: "var(--c-review)" }}>已入人工审核队列</h3>
        <p style={{ fontSize: 13 }}>原因：{manualReview.reason}</p>
      </div>
    );
  }
  return null;
}
```

创建 `web/src/components/TranscriptPanel.tsx`：

```tsx
export function TranscriptPanel({ lines }: { lines: string[] }): JSX.Element | null {
  if (lines.length === 0) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <h4>澄清记录（可追溯，US-005）</h4>
      {lines.map((line, i) => (
        <p key={i} style={{ fontSize: 13, borderBottom: "1px solid var(--c-border)", padding: 4, margin: 0 }}>{line}</p>
      ))}
    </div>
  );
}
```

重写 `web/src/pages/IntakePage.tsx`：

```tsx
import { useEffect, useRef, useState } from "react";
import { InputComposer } from "../components/InputComposer";
import { ProgressStepper } from "../components/ProgressStepper";
import { QuestionCard } from "../components/QuestionCard";
import { WoPreviewCard } from "../components/WoPreviewCard";
import { ReviewPanel } from "../components/ReviewPanel";
import { DeliveryResultCard } from "../components/DeliveryResultCard";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { createRestClient } from "../api/rest";
import { useSessionStore } from "../store/useSessionStore";
import { useAuthStore } from "../store/useAuthStore";
import { useBootstrapStore } from "../store/useBootstrapStore";
import { useUiStore } from "../store/useUiStore";

export interface IntakeSocketLike { send: (type: string, sessionId: string, payload?: Record<string, unknown>) => boolean }

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

export function IntakePage({ socket }: { socket?: IntakeSocketLike | null }): JSX.Element {
  const s = useSessionStore();
  const token = useAuthStore((s2) => s2.token);
  const bootstrap = useBootstrapStore((s2) => s2.bootstrap);
  const setView = useUiStore((s2) => s2.setView);
  const liveSocket = useUiStore((s2) => s2.socket); // 真实连接（自审修正）
  const socketRef = useRef<IntakeSocketLike | null>(socket ?? liveSocket);
  const skipResume = useRef(false); // 预检裁定：本页新建会话不发 resume
  const [humanConfirmed, setHumanConfirmed] = useState(false);

  useEffect(() => {
    socketRef.current = socket ?? liveSocket;
  }, [socket, liveSocket]);

  useEffect(() => {
    // 会话续传：外部设置 sessionId 后自动 resume（Expert/Sessions 页复用）；
    // 本页 submit 新建的会话已显式发 intake_input，跳过 resume 避免多余快照
    if (s.sessionId && s.lastSeq === 0) {
      if (skipResume.current) {
        skipResume.current = false;
      } else {
        socketRef.current?.send("session_resume", s.sessionId, { session_id: s.sessionId });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.sessionId]);

  const threshold = Number(bootstrap?.intake?.review_score_threshold ?? 0.9);

  function submit(text: string): void {
    const sid = s.sessionId || `sess-${Date.now()}`;
    skipResume.current = true; // 预检裁定：本页新建会话跳过自动 resume
    useSessionStore.getState().setSessionId(sid);
    useSessionStore.getState().appendTranscript(`您：${text}`);
    socketRef.current?.send("intake_input", sid, { text });
  }

  function confirmHuman(): void {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useUiStore.getState().toast("身份过期") });
    void rest.post<{ status: string }>("/api/v1/intake/review", {
      session_id: s.sessionId, review_score: s.reviewRecord?.review_score ?? 0, human_confirmed: true,
    }).then(() => setHumanConfirmed(true)).catch((e) => useUiStore.getState().toast(String(e)));
  }

  return (
    <section>
      <p style={{ fontSize: 14 }}>用日常语言描述需求，系统将生成标准 ako1 工单（状态：{s.status}）。</p>
      <InputComposer onSubmit={submit} />
      <ProgressStepper status={s.status} />
      {s.questions.length > 0 && (
        <QuestionCard
          questions={s.questions}
          onAnswer={(answers) => socketRef.current?.send("p0_response", s.sessionId, { round: s.round, answers })}
          onConservative={() => socketRef.current?.send("p0_response", s.sessionId, { round: s.round, answers: [], conservative: true })}
        />
      )}
      {s.draftWo && (
        <WoPreviewCard
          wo={s.draftWo}
          confidenceScore={s.confidenceScore}
          reviewScore={s.reviewRecord?.review_score}
          riskFlag={s.riskFlag}
          onEdit={(draft) => socketRef.current?.send("wo_edit", s.sessionId, { draft_wo: draft })}
          onConfirm={() => socketRef.current?.send("wo_confirm", s.sessionId, {})}
          onDiscard={() => socketRef.current?.send("wo_discard", s.sessionId, {})}
        />
      )}
      {s.reviewRecord && (
        <ReviewPanel review={s.reviewRecord} threshold={threshold} onConfirmHuman={confirmHuman} onConfirmed={humanConfirmed} />
      )}
      <DeliveryResultCard hubAck={s.hubAck} queuedLocal={s.queuedLocal} manualReview={s.manualReview} />
      {s.status === "IDLE" && !s.draftWo && <p style={{ fontSize: 13, color: "var(--c-info)" }}>可前往 <button onClick={() => setView("sessions")}>会话续传</button> 恢复未完成会话。</p>}
      <TranscriptPanel lines={s.transcript} />
    </section>
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npm test -- --run src/pages/IntakePage.test.tsx src/components/QuestionCard.test.tsx`
Expected: PASS（4 + 4 用例）

- [ ] **Step 5: 提交**

```bash
git add web/src/components/ web/src/pages/IntakePage.tsx web/src/pages/IntakePage.test.tsx
git commit -m "feat(web): intake 全流程（澄清/预览/评审/投递组件）"
```

---

### Task 7: ExpertPage / SessionsPage / OpsPage（完整 V1）

**Files:**
- Rewrite: `web/src/pages/ExpertPage.tsx`
- Create: `web/src/pages/SessionsPage.tsx`、`web/src/pages/OpsPage.tsx`
- Test: `web/src/pages/ExpertPage.test.tsx`、`web/src/pages/SessionsPage.test.tsx`、`web/src/pages/OpsPage.test.tsx`

**Interfaces:**
- Consumes: F2 rest/ws、F3 stores、F6 的 WoPreviewCard/ReviewPanel/DeliveryResultCard。
- Produces: 三个页面默认导出。

- [ ] **Step 1: 写失败测试**

创建 `web/src/pages/ExpertPage.test.tsx`：

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ExpertPage } from "./ExpertPage";
import { useSessionStore } from "../store/useSessionStore";

const created = { session_id: "sess-1", status: "REVIEWING", review_record: { review_score: 0.95 } };

vi.mock("../api/rest", () => ({
  createRestClient: () => ({
    post: vi.fn(async () => created),
    get: vi.fn(async () => ({ sessions: [] })),
  }),
}));

beforeEach(() => useSessionStore.getState().reset());

describe("ExpertPage", () => {
  it("提交 8 字段表单 → POST /sessions 并设 sessionId", async () => {
    render(<ExpertPage socket={{ send: vi.fn(() => true) }} />);
    fireEvent.change(screen.getByLabelText("module："), { target: { value: "AKO_quote_agent" } });
    fireEvent.change(screen.getByLabelText("action："), { target: { value: "审计" } });
    fireEvent.change(screen.getByLabelText("scope："), { target: { value: "只动校验" } });
    fireEvent.click(screen.getByRole("button", { name: "提交工单" }));
    await waitFor(() => expect(useSessionStore.getState().sessionId).toBe("sess-1"));
  });
  it("module/action 缺失时提交禁用", () => {
    render(<ExpertPage socket={{ send: vi.fn(() => true) }} />);
    expect(screen.getByRole("button", { name: "提交工单" }).getAttribute("disabled")).not.toBeNull();
  });
});
```

创建 `web/src/pages/SessionsPage.test.tsx`：

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SessionsPage } from "./SessionsPage";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

const sessions = [{ session_id: "sess-1", status: "CLARIFYING", updated_at: "2026-09-01T10:00:00" }];

vi.mock("../api/rest", () => ({
  createRestClient: () => ({ get: vi.fn(async () => ({ sessions })), post: vi.fn(async () => ({})) }),
}));

beforeEach(() => { useSessionStore.getState().reset(); useUiStore.getState().reset(); });

describe("SessionsPage", () => {
  it("点击会话 → 设 sessionId 并切到 intake 视图（自动 resume）", async () => {
    render(<SessionsPage socket={{ send: vi.fn(() => true) }} />);
    await waitFor(() => expect(screen.getByText("sess-1")).toBeDefined());
    fireEvent.click(screen.getByText("sess-1"));
    expect(useSessionStore.getState().sessionId).toBe("sess-1");
    expect(useUiStore.getState().view).toBe("intake");
  });
});
```

创建 `web/src/pages/OpsPage.test.tsx`：

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { OpsPage } from "./OpsPage";

vi.mock("../api/rest", () => ({
  createRestClient: () => ({
    get: vi.fn(async (path: string) => {
      if (path === "/health") return { status: "ok", deps: { hub: { ok: true } } };
      if (path === "/metrics") return { sessions_total: 3, budget: { usage_percent: 1.2 } };
      return { pending: 0, done: 0, failed: 0 };
    }),
    post: vi.fn(async () => ({ flushed: [] })),
  }),
}));

beforeEach(() => vi.useFakeTimers());

describe("OpsPage", () => {
  it("渲染健康灯/指标/队列面板", async () => {
    render(<OpsPage />);
    await waitFor(() => expect(screen.getByText("hub")).toBeDefined());
    expect(screen.getByText(/sessions_total/)).toBeDefined();
    expect(screen.getByText(/pending/)).toBeDefined();
  });
});
```

（Fake timers 与轮询：测试中以 10s 轮询间隔触发一次即可；若轮询 setInterval 与 waitFor 冲突，测试改手动注入数据或缩短间隔——以实测为准并记录。）

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/pages`
Expected: FAIL，`Cannot find module './SessionsPage'` 等

- [ ] **Step 3: 实现三个页面**

重写 `web/src/pages/ExpertPage.tsx`：

```tsx
import { useState } from "react";
import { createRestClient } from "../api/rest";
import { WoPreviewCard } from "../components/WoPreviewCard";
import { ReviewPanel } from "../components/ReviewPanel";
import { DeliveryResultCard } from "../components/DeliveryResultCard";
import { useSessionStore } from "../store/useSessionStore";
import { useAuthStore } from "../store/useAuthStore";
import { useBootstrapStore } from "../store/useBootstrapStore";
import { useUiStore } from "../store/useUiStore";
import type { IntakeSocketLike } from "./IntakePage";

const FIELDS = ["module", "action", "scope", "rules", "prohibitions", "deliverable", "deadline"] as const;
const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

interface CreateResult { session_id: string; status: string; review_record?: { review_score: number; structural_passed: boolean; differences: string[] } }

export function ExpertPage({ socket }: { socket?: IntakeSocketLike | null }): JSX.Element {
  const [form, setForm] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<CreateResult | null>(null);
  const s = useSessionStore();
  const token = useAuthStore((st) => st.token);
  const bootstrap = useBootstrapStore((st) => st.bootstrap);
  const setView = useUiStore((st) => st.setView);
  const liveSocket = useUiStore((st) => st.socket); // 真实连接（自审修正）
  const sendSocket: IntakeSocketLike | null = socket ?? liveSocket;

  const threshold = Number(bootstrap?.intake?.review_score_threshold ?? 0.9);
  const canSubmit = Boolean(form.module && form.action);

  async function submit(): Promise<void> {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useUiStore.getState().toast("身份过期") });
    const draftWo: Record<string, string> = { ...form };
    if (draftWo.rules) draftWo.rules = draftWo.rules.split(/[，,;；]/).map((x) => x.trim()).filter(Boolean);
    if (draftWo.prohibitions) draftWo.prohibitions = draftWo.prohibitions.split(/[，,;；]/).map((x) => x.trim()).filter(Boolean);
    const res = await rest.post<CreateResult>("/api/v1/intake/sessions", { draft_wo: draftWo });
    setCreated(res);
    useSessionStore.getState().setSessionId(res.session_id);
    sendSocket?.send("session_resume", res.session_id, { session_id: res.session_id });
  }

  return (
    <section>
      <h2>专家模式：直接填写 ako1 工单</h2>
      <p style={{ fontSize: 13 }}>绕过自然语言解析，人工填写 8 个刚性字段（工单号由系统生成，US-003）。</p>
      {FIELDS.map((field) => (
        <label key={field} style={{ display: "block", margin: "8px 0" }}>
          {field}：
          <input style={{ width: "100%" }} value={form[field] ?? ""} onChange={(e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))} />
        </label>
      ))}
      <button disabled={!canSubmit} onClick={() => void submit()}>提交工单</button>
      {created && s.draftWo && (
        <>
          <div style={{ marginTop: 12 }}>
            <WoPreviewCard
              wo={s.draftWo}
              confidenceScore={s.confidenceScore}
              reviewScore={s.reviewRecord?.review_score}
              riskFlag={s.riskFlag}
              onEdit={(draft) => sendSocket?.send("wo_edit", s.sessionId, { draft_wo: draft })}
              onConfirm={() => sendSocket?.send("wo_confirm", s.sessionId, {})}
              onDiscard={() => sendSocket?.send("wo_discard", s.sessionId, {})}
            />
          </div>
          {s.reviewRecord && <ReviewPanel review={s.reviewRecord} threshold={threshold} onConfirmHuman={() => useUiStore.getState().toast("请到入口页完成人工确认")} onConfirmed={false} />}
          <DeliveryResultCard hubAck={s.hubAck} queuedLocal={s.queuedLocal} manualReview={s.manualReview} />
        </>
      )}
      {created && !s.draftWo && (
        <p style={{ fontSize: 13, color: "var(--c-info)" }}>
          已创建会话 {created.session_id}（{created.status}）。<button onClick={() => setView("intake")}>到入口页查看工单</button>
        </p>
      )}
    </section>
  );
}
```

创建 `web/src/pages/SessionsPage.tsx`：

```tsx
import { useEffect, useState } from "react";
import { createRestClient } from "../api/rest";
import { useSessionStore } from "../store/useSessionStore";
import { useAuthStore } from "../store/useAuthStore";
import { useUiStore } from "../store/useUiStore";
import type { IntakeSocketLike } from "./IntakePage";

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

interface SessionRow { session_id: string; status: string; updated_at: string }

export function SessionsPage({ socket }: { socket?: IntakeSocketLike | null }): JSX.Element {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [error, setError] = useState("");
  const token = useAuthStore((st) => st.token);
  const setView = useUiStore((st) => st.setView);

  useEffect(() => {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useUiStore.getState().toast("身份过期") });
    rest.get<{ sessions: SessionRow[] }>("/api/v1/intake/sessions")
      .then((r) => setRows(r.sessions))
      .catch((e) => setError(String(e)));
  }, [token]);

  function resume(row: SessionRow): void {
    useSessionStore.getState().setSessionId(row.session_id);
    const live = useUiStore.getState().socket; // 真实连接（自审修正）
    (socket ?? live)?.send("session_resume", row.session_id, { session_id: row.session_id });
    setView("intake");
  }

  return (
    <section>
      <h2>会话续传（断点续传，白皮书 8.4）</h2>
      {error && <p style={{ color: "var(--c-danger)" }}>{error}</p>}
      {rows.length === 0 && !error && <p style={{ fontSize: 13 }}>暂无会话。</p>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {rows.map((r) => (
          <li key={r.session_id} style={{ border: "1px solid var(--c-border)", borderRadius: "var(--radius)", padding: 8, margin: "8px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>
              <strong>{r.session_id}</strong>
              <span style={{ fontSize: 12, marginLeft: 8, color: "var(--c-info)" }}>{r.status} · {r.updated_at}</span>
            </span>
            <button onClick={() => resume(r)}>恢复</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

创建 `web/src/pages/OpsPage.tsx`：

```tsx
import { useEffect, useState } from "react";
import { createRestClient } from "../api/rest";
import { useAuthStore } from "../store/useAuthStore";
import { useUiStore } from "../store/useUiStore";

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";
const POLL_MS = 10_000;

interface Deps { [name: string]: { ok: boolean; latency_ms?: number } }

export function OpsPage(): JSX.Element {
  const token = useAuthStore((st) => st.token);
  const [health, setHealth] = useState<{ status: string; deps: Deps } | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [queue, setQueue] = useState<{ pending: number; done: number; failed: number } | null>(null);
  const [flushing, setFlushing] = useState(false);

  useEffect(() => {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useUiStore.getState().toast("身份过期") });
    let alive = true;
    async function poll(): Promise<void> {
      try {
        const [h, m, q] = await Promise.all([
          rest.get<{ status: string; deps: Deps }>("/health"),
          rest.get<Record<string, unknown>>("/metrics"),
          rest.get<{ pending: number; done: number; failed: number }>("/api/v1/intake/queue/stats"),
        ]);
        if (!alive) return;
        setHealth(h); setMetrics(m); setQueue(q);
      } catch (e) {
        if (alive) useUiStore.getState().toast(`运维面板拉取失败：${String(e)}`);
      }
    }
    void poll();
    const timer = setInterval(() => void poll(), POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [token]);

  async function flush(): Promise<void> {
    setFlushing(true);
    try {
      const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useUiStore.getState().toast("身份过期") });
      const r = await rest.post<{ flushed: string[] }>("/api/v1/intake/queue/flush");
      useUiStore.getState().toast(`已冲刷 ${r.flushed.length} 张工单`);
    } catch (e) {
      useUiStore.getState().toast(`冲刷失败：${String(e)}`);
    } finally {
      setFlushing(false);
    }
  }

  return (
    <section>
      <h2>运维面板</h2>
      <h3>依赖健康</h3>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {health ? Object.entries(health.deps).map(([name, d]) => (
          <li key={name} style={{ margin: "4px 0", fontSize: 14 }}>
            <span style={{ color: d.ok ? "var(--c-success)" : "var(--c-danger)" }}>{d.ok ? "●" : "○"}</span> {name}{d.ok ? "" : "（不可达）"}
          </li>
        )) : <li style={{ fontSize: 13 }}>加载中…</li>}
      </ul>
      <h3>指标（10s 轮询）</h3>
      <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{metrics ? JSON.stringify(metrics, null, 2) : "加载中…"}</pre>
      <h3>本地投递队列</h3>
      {queue ? (
        <p style={{ fontSize: 13 }}>pending {queue.pending} · done {queue.done} · failed {queue.failed}</p>
      ) : <p style={{ fontSize: 13 }}>加载中…</p>}
      <button onClick={() => void flush()} disabled={flushing}>{flushing ? "冲刷中…" : "手动冲刷队列"}</button>
    </section>
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npm test -- --run src/pages`
Expected: PASS（ExpertPage 2 + SessionsPage 1 + OpsPage 1；若 fake timers 与 waitFor 冲突，按测试内注释调整轮询注入方式）

- [ ] **Step 5: 提交**

```bash
git add web/src/pages/ExpertPage.tsx web/src/pages/SessionsPage.tsx web/src/pages/OpsPage.tsx web/src/pages/*.test.tsx
git commit -m "feat(web): 专家模式接入 + 会话续传页 + 运维面板（完整 V1）"
```

---

### Task 8: 验收（E 阶段）：构建、全量测试与 AC 核对

**Files:**
- Test: 全量 `npm test -- --run` + `npm run build`
- Docs: `web/README.md`（可选，前端运行说明）

**Interfaces:**
- Consumes: F1-F7 全部产物。

- [ ] **Step 1: 全量前端测试**

Run: `cd web && npm test -- --run`
Expected: 全部 PASS（schemas/api/store/App/pages/components；旧测试已迁移）

- [ ] **Step 2: 类型与构建**

Run: `cd web && npm run build`
Expected: `tsc -b`（strict）零错误 + `vite build` 产出 `dist/`。若 strict 报错（如 unused、类型收窄），修复并重跑。

- [ ] **Step 3: 后端回归（确认前端未动后端）**

Run: `cd .. && python -m pytest -q`
Expected: 99 passed（1 既有警告）——证明前端改动零后端影响

- [ ] **Step 4: AC 核对清单（写入提交信息附注或本计划自审）**

| AC | 目标 | 前端证据 |
|---|---|---|
| AC-11 首屏 ≤1.5s | 无 UI 库、单 tokens.css、bootstrap 单次拉取 | F4 tokens/AppShell、F5 Login 后拉取 |
| AC-13 反问卡渲染 ≤200ms | WS 直达 store 无轮询 | F3 applyMessage → F6 QuestionCard |
| AC-07 投递零丢失呈现 | queued_local 卡 + OpsPage 队列可见 | F6 DeliveryResultCard / F7 OpsPage |
| AC-08 断点续传 | session_resume + snapshot 重建 + SessionsPage | F3 applySnapshot / F7 SessionsPage |
| AC-27 软熔断呈现 | soft_break 横幅 + 强制专家模式 | F4 AppShell 横幅（强制专家模式由 uiStore.view 在横幅显示时切换） |

- [ ] **Step 5: 提交**

```bash
git add web/
git commit -m "feat(web): 验收阶段构建与测试基线（Phase B-E 完成）"
```

---

## 自审记录

- **Spec 覆盖**：设计第四章 4.1 tokens/4.2 五视图/4.3 组件规格/4.4 store 五切片（F3-F7）；第五章 5.1 登录连接（F5+F4 hook）/5.2 澄清循环（F6）/5.3 投递（F6 wo_confirm 链路）/5.4 续传（F3+F7）；第六章错误处置（F2 401→登出、F4 error toast、F3 镜像 gap）；第七章 7.1 测试分层与 7.2 双端契约（F1/F8）；第八章 Phase B-E 改动清单（F4-F8 对应）。设计 4.3 中"软熔断强制专家模式"在 AppShell 横幅显示时由 uiStore.view 切换实现（F4 Step 3 已含 softBreak 横幅，切换动作在 F8 Step 4 核对项落实）。
- **偏差说明**：① `hello.snapshot` 按 Phase A 实现为"不携带"（快照统一走 resume）——F3 applySnapshot 是唯一快照入口；② `ReviewPanel` 人工确认走 `POST /api/v1/intake/review{human_confirmed:true}`（设计 4.3），随后用户仍须点"确认投递"（wo_confirm）触发实际投递——后端两段式设计，前端如实呈现；③ 测试库：F4-F7 需 `npm i -D @testing-library/react`（若版本冲突改用 react-dom/test-utils，记录实测）。
- **占位符扫描**：无 TBD/TODO；每个代码步骤含完整实现；三个页面测试中"若时序冲突按注释调整"为明确指示而非占位。
- **类型一致性**：`IntakeSocket.send(type, sessionId, payload?)` 在 F2 定义、F4-F7 使用一致；`applyMessage(msg: OutboundMessage)` 在 F3 定义、F4 hook 路由使用一致；`session_resume` 负载 `{session_id}` 与后端 `SessionResumePayload` 一致；`IntakeSocketLike` 接口在 F6 定义、F7 导入复用一致。
