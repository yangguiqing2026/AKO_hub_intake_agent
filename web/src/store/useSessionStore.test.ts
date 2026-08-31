import { describe, expect, it } from "vitest";
import { useSessionStore } from "./useSessionStore";

describe("useSessionStore", () => {
  it("starts a session and resets state", () => {
    useSessionStore.getState().startSession("sess-1");
    expect(useSessionStore.getState().sessionId).toBe("sess-1");
    expect(useSessionStore.getState().status).toBe("PARSING");
    useSessionStore.getState().reset();
    expect(useSessionStore.getState().sessionId).toBe("");
    expect(useSessionStore.getState().status).toBe("IDLE");
  });

  it("switches between questions and preview", () => {
    const questions = [{ qid: "q-1-action", field: "action", text: "动作是？", type: "single_choice" as const, options: ["审计"], required: true }];
    useSessionStore.getState().setQuestions(questions);
    expect(useSessionStore.getState().questions).toHaveLength(1);
    useSessionStore.getState().setPreview({ wo_number: "WO-DRAFT-1" });
    expect(useSessionStore.getState().previewWo?.wo_number).toBe("WO-DRAFT-1");
    expect(useSessionStore.getState().questions).toHaveLength(0);
  });

  it("appends transcript lines", () => {
    useSessionStore.getState().addTranscript("a");
    useSessionStore.getState().addTranscript("b");
    expect(useSessionStore.getState().transcript).toEqual(["a", "b"]);
  });
});

