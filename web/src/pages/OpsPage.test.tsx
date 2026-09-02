import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { OpsPage } from "./OpsPage";

vi.mock("../api/rest", () => ({
  createRestClient: () => ({
    get: vi.fn(async (path: string) => {
      if (path === "/health") return { status: "ok", deps: { hub: { ok: true } } };
      if (path === "/metrics") return { sessions_total: 3, budget: { usage_percent: 1.2 } };
      return { pending: 0, done: 0, failed: 0 };
    }),
    post: vi.fn(async () => ({ flushed: [] })),
  }),
}));

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言。
// 轮询测试实测处理：brief 原方案 vi.useFakeTimers() 与 waitFor 冲突——testing-library 的
// jestFakeTimersAreEnabled() 只识别 jest 全局（vitest 无），waitFor 自身轮询 interval 被 fake 化后
// 永不触发，且 React 调度器同为定时器驱动，DOM 不更新 → 测试 8s 超时挂死（已实测）。
// 按 brief 注释授权改为：真实定时器 + mock rest 直接注入数据，断言首轮 poll 渲染三面板；
// 10s setInterval 随 afterEach(cleanup) 卸载清理，无泄漏。
afterEach(cleanup);

describe("OpsPage", () => {
  it("渲染健康灯/指标/队列面板", async () => {
    render(<OpsPage />);
    await waitFor(() => expect(screen.getByText("hub")).toBeDefined());
    expect(screen.getByText(/sessions_total/)).toBeDefined();
    expect(screen.getByText(/pending/)).toBeDefined();
  });
});
