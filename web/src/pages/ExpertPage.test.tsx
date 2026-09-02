import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ExpertPage } from "./ExpertPage";
import { useSessionStore } from "../store/useSessionStore";

const created = { session_id: "sess-1", status: "REVIEWING", review_record: { review_score: 0.95 } };

vi.mock("../api/rest", () => ({
  createRestClient: () => ({
    post: vi.fn(async () => created),
    get: vi.fn(async () => ({ sessions: [] })),
  }),
}));

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言。
afterEach(cleanup);

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
