import { describe, expect, it } from "vitest";
import { parseServerMessage } from "./client";

describe("parseServerMessage", () => {
  it("parses p0_interrogation", () => {
    const msg = parseServerMessage(
      JSON.stringify({ type: "p0_interrogation", session_id: "s1", questions: [{ qid: "q-1", text: "x" }] }),
    );
    expect(msg.type).toBe("p0_interrogation");
    if (msg.type === "p0_interrogation") {
      expect(msg.questions[0].qid).toBe("q-1");
    }
  });

  it("parses wo_preview with review_score", () => {
    const msg = parseServerMessage(
      JSON.stringify({ type: "wo_preview", session_id: "s1", draft_wo: { wo_number: "WO-DRAFT-1" }, confidence_score: 0.95, review_score: 0.96 }),
    );
    expect(msg.type).toBe("wo_preview");
    if (msg.type === "wo_preview") {
      expect(msg.review_score).toBe(0.96);
      expect(msg.draft_wo.wo_number).toBe("WO-DRAFT-1");
    }
  });

  it("falls back to error for unknown types", () => {
    const msg = parseServerMessage(JSON.stringify({ type: "bogus" }));
    expect(msg.type).toBe("error");
  });
});

