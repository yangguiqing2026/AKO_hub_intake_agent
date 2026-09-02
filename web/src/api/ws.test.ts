import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IntakeSocket } from "./ws";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) { FakeWebSocket.instances.push(this); }
  send(data: string): void { this.sent.push(data); }
  close(): void { this.readyState = 3; this.onclose?.(); }
  static openLatest(): void { const w = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]!; w.readyState = 1; w.onopen?.(); }
  static emit(ws: FakeWebSocket, data: string): void { ws.onmessage?.({ data }); }
}

beforeEach(() => { FakeWebSocket.instances = []; vi.stubGlobal("WebSocket", FakeWebSocket); vi.useFakeTimers(); });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("IntakeSocket", () => {
  it("连接后按信封解析出站消息并回调", () => {
    const onMessage = vi.fn();
    const s = new IntakeSocket({ url: "ws://x", onMessage });
    s.connect();
    FakeWebSocket.openLatest();
    FakeWebSocket.emit(FakeWebSocket.instances[0], JSON.stringify({ v: 2, type: "status", session_id: "s1", seq: 1, ts: "t", payload: { status: "PARSING" } }));
    expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({ type: "status", seq: 1 }));
  });

  it("解析失败的消息被静默丢弃（不断连）", () => {
    const onMessage = vi.fn();
    const s = new IntakeSocket({ url: "ws://x", onMessage });
    s.connect();
    FakeWebSocket.openLatest();
    FakeWebSocket.emit(FakeWebSocket.instances[0], "not-json");
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("断线指数退避重连（1s→2s→4s，封顶 30s）", () => {
    const onStateChange = vi.fn();
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn(), onStateChange });
    s.connect();
    FakeWebSocket.openLatest();
    FakeWebSocket.instances[0].close(); // onclose → 退避重连
    expect(onStateChange).toHaveBeenCalledWith("reconnecting");
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(FakeWebSocket.instances).toHaveLength(2);
    FakeWebSocket.instances[1].close(); // 新连接再次断开 → 2s 退避
    vi.advanceTimersByTime(2000);
    expect(FakeWebSocket.instances).toHaveLength(3);
    FakeWebSocket.instances[2].close(); // 第三次断开 → 4s 退避
    vi.advanceTimersByTime(4000);
    expect(FakeWebSocket.instances).toHaveLength(4);
  });

  it("close() 后不再重连", () => {
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn() });
    s.connect();
    FakeWebSocket.openLatest();
    s.close();
    vi.advanceTimersByTime(100000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("send 按 v2 信封发送；未连接时返回 false", () => {
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn() });
    expect(s.send("ping", "")).toBe(false);
    s.connect();
    FakeWebSocket.openLatest();
    expect(s.send("intake_input", "s1", { text: "修复报价模块的bug，只动校验逻辑，不动数据库" })).toBe(true);
    expect(JSON.parse(FakeWebSocket.instances[0].sent[0])).toEqual({ v: 2, type: "intake_input", session_id: "s1", payload: { text: "修复报价模块的bug，只动校验逻辑，不动数据库" } });
  });

  it("stream_chunk 累计 16KB 自动发 stream_ack", () => {
    const s = new IntakeSocket({ url: "ws://x", onMessage: vi.fn(), streamAckBytes: 5 });
    s.connect();
    FakeWebSocket.openLatest();
    const ws = FakeWebSocket.instances[0];
    const big = "x".repeat(6);
    FakeWebSocket.emit(ws, JSON.stringify({ v: 2, type: "stream_chunk", session_id: "s1", seq: 1, ts: "t", payload: { stream_id: "st1", kind: "chunk", data: big } }));
    const ack = ws.sent.find((m) => JSON.parse(m).type === "stream_ack");
    expect(ack).toBeDefined();
    expect(JSON.parse(ack!).payload.bytes).toBeGreaterThanOrEqual(5);
  });
});
