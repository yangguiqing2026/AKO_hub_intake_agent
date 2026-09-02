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
  onGapRef: (() => void) | null;
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
    // 设计 3.3：session_snapshot 无条件重建镜像，不受 seq 去重/跳跃规则约束
    if (msg.type === "session_snapshot") {
      get().applySnapshot(msg.payload.state, msg.payload.seq);
      return;
    }
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
    queuedLocal: null, manualReview: null, transcript: [], needsResume: false, onGapRef: null,
  }),
}));
