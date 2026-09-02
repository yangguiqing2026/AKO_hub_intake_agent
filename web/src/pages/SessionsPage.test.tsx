import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SessionsPage } from "./SessionsPage";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

const sessions = [{ session_id: "sess-1", status: "CLARIFYING", updated_at: "2026-09-01T10:00:00" }];

vi.mock("../api/rest", () => ({
  createRestClient: () => ({ get: vi.fn(async () => ({ sessions })), post: vi.fn(async () => ({})) }),
}));

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言。
afterEach(cleanup);

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
