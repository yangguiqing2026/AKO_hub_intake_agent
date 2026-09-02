import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { IntakePage } from "./IntakePage";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

// 终审 C2 测试：确认动作依赖 POST /review，mock rest 注入。
vi.mock("../api/rest", () => ({
  createRestClient: () => ({
    post: vi.fn(async () => ({ status: "ok" })),
    get: vi.fn(async () => ({})),
  }),
}));

function makeSocket() {
  const sent: { type: string; sessionId: string; payload: Record<string, unknown> }[] = [];
  const socket = { send: (type: string, sessionId: string, payload: Record<string, unknown> = {}) => { sent.push({ type, sessionId, payload }); return true; } };
  return { socket, sent };
}

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言。
afterEach(cleanup);

beforeEach(() => { useSessionStore.getState().reset(); useUiStore.getState().reset(); });

describe("IntakePage", () => {
  it("提交输入发送 intake_input 并生成会话号", async () => {
    const { socket, sent } = makeSocket();
    render(<IntakePage socket={socket} />);
    fireEvent.change(screen.getByPlaceholderText(/描述你的需求/), { target: { value: "修复报价模块的bug，只动校验逻辑，不动数据库" } });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].type).toBe("intake_input");
    expect((sent[0].payload.text as string).length).toBeGreaterThanOrEqual(10);
  });
  it("短文本（<10 字符）不发送并提示", () => {
    const { socket, sent } = makeSocket();
    render(<IntakePage socket={socket} />);
    fireEvent.change(screen.getByPlaceholderText(/描述你的需求/), { target: { value: "太短" } });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
    expect(sent).toHaveLength(0);
    expect(screen.getByText(/文本须 10~2000 字符/)).toBeDefined();
  });
  it("wo_preview 更新后人工确认状态重置（终审 C2）", async () => {
    const { socket } = makeSocket();
    render(<IntakePage socket={socket} />);
    act(() => {
      useSessionStore.getState().setSessionId("s1");
      useSessionStore.getState().applyMessage({ v: 2, type: "wo_preview", session_id: "s1", seq: 1, ts: "t", req_id: "", payload: { draft_wo: { wo_number: "WO-DRAFT-1" }, confidence_score: 0.8, review_record: { review_score: 0.85, structural_passed: true, differences: [], reviewed_at: "t1" }, risk_flag: "", actions: ["confirm", "edit", "discard"] } });
      useSessionStore.getState().applyMessage({ v: 2, type: "status", session_id: "s1", seq: 2, ts: "t", req_id: "", payload: { status: "REVIEWING" } });
    });
    // 点击"人工确认通过"（POST /review mock 成功）→ 已确认
    fireEvent.click(screen.getByRole("button", { name: "人工确认通过" }));
    await waitFor(() => expect(screen.getByText("已确认，请继续投递。")).toBeDefined());
    // 确认后新预览（同会话 seq 续）→ 门禁重置，按钮重新出现
    act(() => {
      useSessionStore.getState().applyMessage({ v: 2, type: "wo_preview", session_id: "s1", seq: 3, ts: "t", req_id: "", payload: { draft_wo: { wo_number: "WO-DRAFT-1", scope: "只动A" }, confidence_score: 0.8, review_record: { review_score: 0.85, structural_passed: true, differences: [], reviewed_at: "t2" }, risk_flag: "", actions: ["confirm", "edit", "discard"] } });
    });
    expect(screen.getByRole("button", { name: "人工确认通过" })).toBeDefined();
  });
});
