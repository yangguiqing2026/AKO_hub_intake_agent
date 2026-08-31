export type ServerMessage =
  | { type: "p0_interrogation"; session_id: string; questions: Question[] }
  | { type: "wo_preview"; session_id: string; draft_wo: Record<string, unknown>; confidence_score: number; review_score?: number }
  | { type: "status"; session_id: string; status: string }
  | { type: "error"; error: string };

export interface Question {
  qid: string;
  field: string;
  text: string;
  type: "single_choice" | "open" | "confirm";
  options: string[];
  required: boolean;
}

export function parseServerMessage(raw: string): ServerMessage {
  const data: unknown = JSON.parse(raw);
  if (typeof data !== "object" || data === null) {
    throw new Error("invalid message payload");
  }
  const msg = data as Record<string, unknown>;
  const type = String(msg.type ?? "");
  const sessionId = String(msg.session_id ?? "");
  if (type === "p0_interrogation") {
    return { type, session_id: sessionId, questions: (msg.questions as Question[]) ?? [] };
  }
  if (type === "wo_preview") {
    return {
      type,
      session_id: sessionId,
      draft_wo: (msg.draft_wo as Record<string, unknown>) ?? {},
      confidence_score: Number(msg.confidence_score ?? 0),
      review_score: msg.review_score === undefined ? undefined : Number(msg.review_score),
    };
  }
  if (type === "status") {
    return { type, session_id: sessionId, status: String(msg.status ?? "") };
  }
  return { type: "error", error: String(msg.error ?? "unknown error") };
}

export class IntakeSocket {
  private socket: WebSocket | null = null;
  constructor(private readonly url: string, private readonly onMessage: (msg: ServerMessage) => void) {}

  connect(): void {
    this.socket = new WebSocket(this.url);
    this.socket.onmessage = (event: MessageEvent<string>): void => {
      this.onMessage(parseServerMessage(event.data));
    };
  }

  send(type: string, payload: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type, ...payload }));
    }
  }

  close(): void {
    this.socket?.close();
  }
}

