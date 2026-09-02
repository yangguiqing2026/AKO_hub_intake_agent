interface Props {
  hubAck: Record<string, unknown> | null;
  queuedLocal: { woNumber: string; nextRetryAt: string } | null;
  manualReview: { draftWo: Record<string, unknown>; reason: string } | null;
}

export function DeliveryResultCard({ hubAck, queuedLocal, manualReview }: Props): JSX.Element | null {
  if (hubAck) {
    return (
      <div style={{ border: "1px solid var(--c-success)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
        <h3 style={{ marginTop: 0, color: "var(--c-success)" }}>已投递 Hub</h3>
        <p style={{ fontSize: 13 }}>正式编号：{String(hubAck.wo_number ?? "—")} · 队列位置：{String(hubAck.queue_position ?? "—")} · 追踪号：{String(hubAck.hub_trace_id ?? "—")}</p>
      </div>
    );
  }
  if (queuedLocal) {
    return (
      <div style={{ border: "1px solid var(--c-warning)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
        <h3 style={{ marginTop: 0, color: "var(--c-warning)" }}>Hub 不可达，已入本地队列（零丢失）</h3>
        <p style={{ fontSize: 13 }}>工单 {queuedLocal.woNumber} · 下次重试 {queuedLocal.nextRetryAt || "按退避策略"}</p>
      </div>
    );
  }
  if (manualReview) {
    return (
      <div style={{ border: "1px solid var(--c-review)", borderRadius: "var(--radius)", padding: 12, marginTop: 12, background: "var(--c-card)" }}>
        <h3 style={{ marginTop: 0, color: "var(--c-review)" }}>已入人工审核队列</h3>
        <p style={{ fontSize: 13 }}>原因：{manualReview.reason}</p>
      </div>
    );
  }
  return null;
}
