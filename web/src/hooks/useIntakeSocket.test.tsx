import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { useIntakeSocket } from "./useIntakeSocket";
import { useAuthStore } from "../store/useAuthStore";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";
import type { OutboundMessage } from "../schemas/ws";

// 保留构造选项的 IntakeSocket mock：构造函数捕获 opts（onOpen/onMessage），实例 send 供断言。
interface CapturedOpts {
  onOpen?: () => void;
  onMessage?: (m: OutboundMessage) => void;
}

const captured: CapturedOpts = {};
const instances: { send: Mock }[] = [];

vi.mock("../api/ws", () => ({
  IntakeSocket: class {
    constructor(opts: CapturedOpts) {
      Object.assign(captured, opts);
      instances.push(this);
    }
    connect = vi.fn();
    close = vi.fn();
    send = vi.fn((_type: string, _sessionId: string) => true);
  },
}));

// 取最近一次 mock 实例的 send
function capturedSend(): Mock {
  return instances[instances.length - 1].send;
}

function Harness(): null {
  useIntakeSocket();
  return null;
}

// vitest 未开 globals，RTL 自动 cleanup 不生效，显式注册避免多次 render 累积干扰断言。
afterEach(cleanup);

beforeEach(() => {
  instances.length = 0;
  vi.clearAllMocks();
  useAuthStore.getState().logout();
  useSessionStore.getState().reset();
  useUiStore.getState().reset();
});

describe("useIntakeSocket", () => {
  it("gap 时经 onGap 发送 session_resume", () => {
    useAuthStore.getState().login("tok", "a");
    useSessionStore.getState().setSessionId("s1");
    useSessionStore.getState().applyMessage({ v: 2, type: "status", session_id: "s1", seq: 1, ts: "t", req_id: "", payload: { status: "PARSING" } });
    render(<Harness />);
    act(() => {
      captured.onMessage?.({ v: 2, type: "status", session_id: "s1", seq: 3, ts: "t", req_id: "", payload: { status: "DELIVERED" } });
    });
    expect(capturedSend()).toHaveBeenCalledWith("session_resume", "s1", { session_id: "s1" });
  });

  it("onOpen 时已有会话且 lastSeq>0 → 重连对账 resume", () => {
    useAuthStore.getState().login("tok", "a");
    useSessionStore.getState().setSessionId("s1");
    useSessionStore.getState().applyMessage({ v: 2, type: "status", session_id: "s1", seq: 1, ts: "t", req_id: "", payload: { status: "PARSING" } });
    render(<Harness />);
    act(() => captured.onOpen?.());
    expect(capturedSend()).toHaveBeenCalledWith("auth", "", { token: "tok" });
    expect(capturedSend()).toHaveBeenCalledWith("session_resume", "s1", { session_id: "s1" });
  });

  it("soft_break{active:true} → 升横幅（snake→camel 映射）", () => {
    render(<Harness />);
    act(() => {
      captured.onMessage?.({ v: 2, type: "soft_break", session_id: "", seq: 1, ts: "t", req_id: "", payload: { usage_percent: 5.0, monthly_quota_tokens: 100000, active: true } });
    });
    const sb = useUiStore.getState().softBreak;
    expect(sb).not.toBeNull();
    expect(sb?.usagePercent).toBe(5.0);
    expect(sb?.monthlyQuotaTokens).toBe(100000);
  });

  it("soft_break{active:false} → 横幅清除", () => {
    useUiStore.getState().pushSoftBreak({ usagePercent: 5.0, monthlyQuotaTokens: 100000 });
    render(<Harness />);
    act(() => {
      captured.onMessage?.({ v: 2, type: "soft_break", session_id: "", seq: 1, ts: "t", req_id: "", payload: { usage_percent: 0.5, monthly_quota_tokens: 1000000, active: false } });
    });
    expect(useUiStore.getState().softBreak).toBeNull();
  });

  it("hello 快照 soft_break_active=true → 升横幅（对账通道）", () => {
    render(<Harness />);
    act(() => {
      captured.onMessage?.({
        v: 2, type: "hello", session_id: "", seq: 1, ts: "t", req_id: "",
        payload: {
          protocol_version: 2, server_time: "t", session_id: "",
          bootstrap: {
            agent_id: "AKO_hub_intake_agent", version: "0.1.0", terms: [],
            intake: {}, llm: {}, knowledge_enabled: false, identity_required: false, ws: {}, observability: {},
            budget: { soft_break_active: true, usage_percent: 5.0, monthly_quota_tokens: 100000 },
          },
        },
      });
    });
    const sb = useUiStore.getState().softBreak;
    expect(sb).not.toBeNull();
    expect(sb?.usagePercent).toBe(5.0);
  });

  it("hello 快照 soft_break_active=false → 横幅清除（对账事实源）", () => {
    useUiStore.getState().pushSoftBreak({ usagePercent: 5.0, monthlyQuotaTokens: 100000 });
    render(<Harness />);
    act(() => {
      captured.onMessage?.({
        v: 2, type: "hello", session_id: "", seq: 1, ts: "t", req_id: "",
        payload: {
          protocol_version: 2, server_time: "t", session_id: "",
          bootstrap: {
            agent_id: "AKO_hub_intake_agent", version: "0.1.0", terms: [],
            intake: {}, llm: {}, knowledge_enabled: false, identity_required: false, ws: {}, observability: {},
            budget: { soft_break_active: false },
          },
        },
      });
    });
    expect(useUiStore.getState().softBreak).toBeNull();
  });
});
