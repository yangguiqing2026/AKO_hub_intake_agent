import { useState } from "react";
import { createRestClient } from "../api/rest";
import { WoPreviewCard } from "../components/WoPreviewCard";
import { ReviewPanel } from "../components/ReviewPanel";
import { DeliveryResultCard } from "../components/DeliveryResultCard";
import { useSessionStore } from "../store/useSessionStore";
import { useAuthStore } from "../store/useAuthStore";
import { useBootstrapStore } from "../store/useBootstrapStore";
import { useUiStore } from "../store/useUiStore";
import type { IntakeSocketLike } from "./IntakePage";

const FIELDS = ["module", "action", "scope", "rules", "prohibitions", "deliverable", "deadline"] as const;
const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

interface CreateResult { session_id: string; status: string; review_record?: { review_score: number; structural_passed: boolean; differences: string[] } }

export function ExpertPage({ socket }: { socket?: IntakeSocketLike | null }): JSX.Element {
  const [form, setForm] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<CreateResult | null>(null);
  const s = useSessionStore();
  const token = useAuthStore((st) => st.token);
  const bootstrap = useBootstrapStore((st) => st.bootstrap);
  const setView = useUiStore((st) => st.setView);
  const liveSocket = useUiStore((st) => st.socket); // 真实连接（自审修正）
  const sendSocket: IntakeSocketLike | null = socket ?? liveSocket;

  const threshold = Number(bootstrap?.intake?.review_score_threshold ?? 0.9);
  const canSubmit = Boolean(form.module && form.action);

  async function submit(): Promise<void> {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useUiStore.getState().toast("身份过期") });
    // rules/prohibitions 切分后为数组（TS strict：索引值类型收窄为 string | string[]）
    const draftWo: Record<string, string | string[]> = { ...form };
    if (form.rules) draftWo.rules = form.rules.split(/[，,;；]/).map((x) => x.trim()).filter(Boolean);
    if (form.prohibitions) draftWo.prohibitions = form.prohibitions.split(/[，,;；]/).map((x) => x.trim()).filter(Boolean);
    const res = await rest.post<CreateResult>("/api/v1/intake/sessions", { draft_wo: draftWo });
    setCreated(res);
    useSessionStore.getState().setSessionId(res.session_id);
    sendSocket?.send("session_resume", res.session_id, { session_id: res.session_id });
  }

  return (
    <section>
      <h2>专家模式：直接填写 ako1 工单</h2>
      <p style={{ fontSize: 13 }}>绕过自然语言解析，人工填写 8 个刚性字段（工单号由系统生成，US-003）。</p>
      {FIELDS.map((field) => (
        <label key={field} style={{ display: "block", margin: "8px 0" }}>
          {field}：
          <input style={{ width: "100%" }} value={form[field] ?? ""} onChange={(e) => setForm((prev) => ({ ...prev, [field]: e.target.value }))} />
        </label>
      ))}
      <button disabled={!canSubmit} onClick={() => void submit()}>提交工单</button>
      {created && s.draftWo && (
        <>
          <div style={{ marginTop: 12 }}>
            <WoPreviewCard
              wo={s.draftWo}
              confidenceScore={s.confidenceScore}
              reviewScore={s.reviewRecord?.review_score}
              riskFlag={s.riskFlag}
              onEdit={(draft) => sendSocket?.send("wo_edit", s.sessionId, { draft_wo: draft })}
              onConfirm={() => sendSocket?.send("wo_confirm", s.sessionId, {})}
              onDiscard={() => sendSocket?.send("wo_discard", s.sessionId, {})}
            />
          </div>
          {s.reviewRecord && <ReviewPanel review={s.reviewRecord} threshold={threshold} onConfirmHuman={() => useUiStore.getState().toast("请到入口页完成人工确认")} onConfirmed={false} />}
          <DeliveryResultCard hubAck={s.hubAck} queuedLocal={s.queuedLocal} manualReview={s.manualReview} />
        </>
      )}
      {created && !s.draftWo && (
        <p style={{ fontSize: 13, color: "var(--c-info)" }}>
          已创建会话 {created.session_id}（{created.status}）。<button onClick={() => setView("intake")}>到入口页查看工单</button>
        </p>
      )}
    </section>
  );
}
