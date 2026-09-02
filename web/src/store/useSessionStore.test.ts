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
    useSessionStore.getState().applyMessage({ v: 2, type: "wo_preview", session_id: "s1", seq: 1, ts: "t", req_id: "", payload: { draft_wo: { wo_number: "WO-DRAFT-1" }, confidence_score: 0.95, review_record: { review_score: 0.96, structural_passed: true, differences: [], reviewed_at: "" }, risk_flag: "", actions: ["confirm", "edit", "discard"] } });
    expect(useSessionStore.getState().draftWo).toEqual({ wo_number: "WO-DRAFT-1" });
    useSessionStore.getState().applyMessage({ v: 2, type: "hub_ack", session_id: "s1", seq: 2, ts: "t", req_id: "", payload: { ack: { wo_number: "WO-HAI-1" } } });
    expect(useSessionStore.getState().hubAck).toEqual({ wo_number: "WO-HAI-1" });
  });

  it("其他会话消息被忽略", () => {
    useSessionStore.getState().applyMessage(statusMsg("s1", 1, "PARSING"));
    useSessionStore.getState().applyMessage(statusMsg("other", 1, "DELIVERED"));
    expect(useSessionStore.getState().status).toBe("PARSING");
  });

  it("status IDLE 清除草稿/回执镜像（终审 I6）", () => {
    useSessionStore.getState().applyMessage({ v: 2, type: "wo_preview", session_id: "s1", seq: 1, ts: "t", req_id: "", payload: { draft_wo: { wo_number: "WO-DRAFT-1" }, confidence_score: 0.9, review_record: { review_score: 0.95, structural_passed: true, differences: [], reviewed_at: "" }, risk_flag: "", actions: ["confirm", "edit", "discard"] } });
    useSessionStore.getState().applyMessage({ v: 2, type: "status", session_id: "s1", seq: 2, ts: "t", req_id: "", payload: { status: "IDLE" } });
    const s = useSessionStore.getState();
    expect(s.draftWo).toBeNull();
    expect(s.hubAck).toBeNull();
  });

  it("setSessionId 清除上一会话镜像（终审 I6）", () => {
    useSessionStore.getState().applyMessage({ v: 2, type: "hub_ack", session_id: "s1", seq: 1, ts: "t", req_id: "", payload: { ack: { wo_number: "WO-HAI-1" } } });
    useSessionStore.getState().setSessionId("s2");
    const s = useSessionStore.getState();
    expect(s.sessionId).toBe("s2");
    expect(s.hubAck).toBeNull();
    expect(s.transcript).toEqual([]);
  });
});
