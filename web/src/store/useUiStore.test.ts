import { beforeEach, describe, expect, it } from "vitest";
import { useUiStore } from "./useUiStore";

beforeEach(() => useUiStore.getState().reset());

describe("useUiStore", () => {
  it("主题切换 toggleTheme", () => {
    expect(useUiStore.getState().theme).toBe("light");
    useUiStore.getState().toggleTheme();
    expect(useUiStore.getState().theme).toBe("dark");
  });
  it("toast 追加与关闭", () => {
    useUiStore.getState().toast("hello");
    const id = useUiStore.getState().toasts[0].id;
    useUiStore.getState().dismissToast(id);
    expect(useUiStore.getState().toasts).toHaveLength(0);
  });
  it("软熔断 push 与清除", () => {
    useUiStore.getState().pushSoftBreak({ usagePercent: 6.0, monthlyQuotaTokens: 1000000 });
    expect(useUiStore.getState().softBreak).not.toBeNull();
    useUiStore.getState().clearSoftBreak();
    expect(useUiStore.getState().softBreak).toBeNull();
  });
});
