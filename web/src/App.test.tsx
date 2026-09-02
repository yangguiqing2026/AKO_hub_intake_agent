import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { App } from "./App";
import { useAuthStore } from "./store/useAuthStore";
import { useUiStore } from "./store/useUiStore";

// 用 @testing-library/react 渲染；stub IntakeSocket 避免 jsdom 无 WebSocket。
vi.mock("./api/ws", () => ({ IntakeSocket: class { connect = vi.fn(); close = vi.fn(); send = vi.fn(); } }));

beforeEach(() => {
  useAuthStore.getState().logout();
  useUiStore.getState().reset();
});

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言。
afterEach(cleanup);

describe("AppShell", () => {
  it("未登录时渲染登录页", () => {
    render(<App />);
    expect(screen.getByText("登录")).toBeDefined();
  });
  it("登录后导航可切换视图", () => {
    act(() => useAuthStore.getState().login("dev-token", "admin"));
    act(() => useUiStore.getState().setView("ops"));
    render(<App />);
    // nav 按钮与 OpsPage 占位页都渲染“运维面板”（共 2 处）；若视图未切换则仅 nav 1 处。
    expect(screen.getAllByText("运维面板")).toHaveLength(2);
  });
});
