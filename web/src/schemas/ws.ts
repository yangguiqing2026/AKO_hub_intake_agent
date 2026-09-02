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
  z.object({ ...outEnvelope, type: z.literal("soft_break"), payload: z.object({ usage_percent: z.number(), monthly_quota_tokens: z.number(), active: z.boolean() }) }),
  z.object({ ...outEnvelope, type: z.literal("error"), payload: z.object({ code: z.string(), message: z.string() }) }),
  z.object({ ...outEnvelope, type: z.literal("pong"), payload: emptyPayload }),
]);
export type OutboundMessage = z.infer<typeof outboundEnvelope>;
export type Question = z.infer<typeof question>;
export type ReviewRecord = z.infer<typeof reviewRecord>;
export type BootstrapConfig = z.infer<typeof bootstrapConfig>;
