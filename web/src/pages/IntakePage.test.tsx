import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { IntakePage } from "./IntakePage";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

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
});
