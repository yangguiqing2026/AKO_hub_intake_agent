import { outboundEnvelope, type OutboundMessage } from "../schemas/ws";

export interface IntakeSocketOptions {
  url: string;
  onMessage: (msg: OutboundMessage) => void;
  onStateChange?: (state: "connecting" | "open" | "reconnecting" | "closed") => void;
  onOpen?: () => void;
  heartbeatSeconds?: number;
  streamAckBytes?: number;
  maxBackoffSeconds?: number;
}

export class IntakeSocket {
  private ws: WebSocket | null = null;
  private backoffMs = 1000;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByUser = false;
  private streamBytes = 0;
  private streamId = "";

  constructor(private readonly opts: IntakeSocketOptions) {}

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  close(): void {
    this.closedByUser = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.opts.onStateChange?.("closed");
  }

  send(type: string, sessionId: string, payload: Record<string, unknown> = {}): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify({ v: 2, type, session_id: sessionId, payload }));
    return true;
  }

  private open(): void {
    this.opts.onStateChange?.(this.ws ? "reconnecting" : "connecting");
    const ws = new WebSocket(this.opts.url);
    this.ws = ws;
    ws.onopen = (): void => {
      this.opts.onStateChange?.("open");
      this.backoffMs = 1000;
      this.startHeartbeat();
      this.opts.onOpen?.();
    };
    ws.onmessage = (e: MessageEvent<string>): void => this.handleRaw(e.data);
    ws.onclose = (): void => {
      this.stopHeartbeat();
      if (this.closedByUser) return;
      this.scheduleReconnect();
    };
    ws.onerror = (): void => ws.close();
  }

  private scheduleReconnect(): void {
    this.opts.onStateChange?.("reconnecting");
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.closedByUser) return;
      this.open();
    }, this.backoffMs);
    this.backoffMs = Math.min(this.backoffMs * 2, (this.opts.maxBackoffSeconds ?? 30) * 1000);
  }

  private handleRaw(raw: string): void {
    let msg: OutboundMessage;
    try {
      msg = outboundEnvelope.parse(JSON.parse(raw));
    } catch {
      return;
    }
    if (msg.type === "stream_chunk") {
      this.trackStream(msg.payload.stream_id, String(msg.payload.data ?? "").length, msg.payload.kind);
    }
    if (msg.type === "pong") return;
    this.opts.onMessage(msg);
  }

  private trackStream(streamId: string, bytes: number, kind: "start" | "chunk" | "end"): void {
    if (kind === "start") { this.streamId = streamId; this.streamBytes = 0; return; }
    if (kind === "end") { this.streamBytes = 0; return; }
    this.streamBytes += bytes;
    if (this.streamBytes >= (this.opts.streamAckBytes ?? 16384)) {
      this.send("stream_ack", "", { stream_id: this.streamId || streamId, bytes: this.streamBytes });
      this.streamBytes = 0;
    }
  }

  private startHeartbeat(): void {
    const hb = (this.opts.heartbeatSeconds ?? 30) * 1000;
    this.heartbeatTimer = setInterval(() => { this.send("ping", ""); }, hb);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }
}
