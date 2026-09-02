import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LoginPage } from "./LoginPage";
import { useAuthStore } from "../store/useAuthStore";

vi.mock("../api/rest", () => ({
  createRestClient: () => ({
    post: vi.fn(async (path: string) => {
      if (path === "/api/v1/identity/login") return { token: "tok-1", expires_at: "", identity: { account: "a" } };
      throw new Error("unexpected");
    }),
    get: vi.fn(async () => ({})),
  }),
}));

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言（同 App.test.tsx）。
afterEach(cleanup);

beforeEach(() => useAuthStore.getState().logout());

describe("LoginPage", () => {
  it("账号+六位指纹校验：不足 6 位提示", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByPlaceholderText("账号"), { target: { value: "admin" } });
    fireEvent.change(screen.getByPlaceholderText("六位指纹"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(screen.getByText(/六位数字/)).toBeDefined());
  });
  it("登录成功写入 auth store", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByPlaceholderText("账号"), { target: { value: "admin" } });
    fireEvent.change(screen.getByPlaceholderText("六位指纹"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(useAuthStore.getState().status).toBe("logged_in"));
    expect(useAuthStore.getState().token).toBe("tok-1");
  });
});
