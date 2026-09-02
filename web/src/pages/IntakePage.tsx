import { useEffect, useRef, useState } from "react";
import { InputComposer } from "../components/InputComposer";
import { ProgressStepper } from "../components/ProgressStepper";
import { QuestionCard } from "../components/QuestionCard";
import { WoPreviewCard } from "../components/WoPreviewCard";
import { ReviewPanel } from "../components/ReviewPanel";
import { DeliveryResultCard } from "../components/DeliveryResultCard";
import { TranscriptPanel } from "../components/TranscriptPanel";
import { createRestClient } from "../api/rest";
import { useSessionStore } from "../store/useSessionStore";
import { useAuthStore } from "../store/useAuthStore";
import { useBootstrapStore } from "../store/useBootstrapStore";
import { useUiStore } from "../store/useUiStore";

export interface IntakeSocketLike { send: (type: string, sessionId: string, payload?: Record<string, unknown>) => boolean }

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

export function IntakePage({ socket }: { socket?: IntakeSocketLike | null }): JSX.Element {
  const s = useSessionStore();
  const token = useAuthStore((s2) => s2.token);
  const bootstrap = useBootstrapStore((s2) => s2.bootstrap);
  const setView = useUiStore((s2) => s2.setView);
  const liveSocket = useUiStore((s2) => s2.socket); // 真实连接（自审修正）
  const socketRef = useRef<IntakeSocketLike | null>(socket ?? liveSocket);
  const skipResume = useRef(false); // 预检裁定：本页新建会话不发 resume
  const [humanConfirmed, setHumanConfirmed] = useState(false);

  useEffect(() => {
    socketRef.current = socket ?? liveSocket;
  }, [socket, liveSocket]);

  useEffect(() => {
    setHumanConfirmed(false); // 终审 C2：新预览（新草稿）到达即重置人工确认
  }, [s.draftWo]);

  useEffect(() => {
    // 会话续传：外部设置 sessionId 后自动 resume（Expert/Sessions 页复用）；
    // 本页 submit 新建的会话已显式发 intake_input，跳过 resume 避免多余快照
    if (s.sessionId && s.lastSeq === 0) {
      if (skipResume.current) {
        skipResume.current = false;
      } else {
        socketRef.current?.send("session_resume", s.sessionId, { session_id: s.sessionId });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.sessionId]);

  const threshold = Number(bootstrap?.intake?.review_score_threshold ?? 0.9);

  function submit(text: string): void {
    const sid = s.sessionId || `sess-${Date.now()}`;
    skipResume.current = true; // 预检裁定：本页新建会话跳过自动 resume
    useSessionStore.getState().setSessionId(sid);
    useSessionStore.getState().appendTranscript(`您：${text}`);
    socketRef.current?.send("intake_input", sid, { text });
  }

  function confirmHuman(): void {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useAuthStore.getState().logout() });
    void rest.post<{ status: string }>("/api/v1/intake/review", {
      session_id: s.sessionId, review_score: s.reviewRecord?.review_score ?? 0, human_confirmed: true,
    }).then(() => setHumanConfirmed(true)).catch((e) => useUiStore.getState().toast(String(e)));
  }

  return (
    <section>
      <p style={{ fontSize: 14 }}>用日常语言描述需求，系统将生成标准 ako1 工单（状态：{s.status}）。</p>
      <InputComposer onSubmit={submit} />
      <ProgressStepper status={s.status} />
      {s.questions.length > 0 && (
        <QuestionCard
          questions={s.questions}
          onAnswer={(answers) => socketRef.current?.send("p0_response", s.sessionId, { round: s.round, answers })}
          onConservative={() => socketRef.current?.send("p0_response", s.sessionId, { round: s.round, answers: [], conservative: true })}
        />
      )}
      {s.draftWo && (
        <WoPreviewCard
          wo={s.draftWo}
          confidenceScore={s.confidenceScore}
          reviewScore={s.reviewRecord?.review_score}
          riskFlag={s.riskFlag}
          onEdit={(draft) => socketRef.current?.send("wo_edit", s.sessionId, { draft_wo: draft })}
          onConfirm={() => socketRef.current?.send("wo_confirm", s.sessionId, {})}
          onDiscard={() => socketRef.current?.send("wo_discard", s.sessionId, {})}
        />
      )}
      {s.reviewRecord && (
        <ReviewPanel review={s.reviewRecord} threshold={threshold} onConfirmHuman={confirmHuman} onConfirmed={humanConfirmed} />
      )}
      <DeliveryResultCard hubAck={s.hubAck} queuedLocal={s.queuedLocal} manualReview={s.manualReview} />
      {s.status === "IDLE" && !s.draftWo && <p style={{ fontSize: 13, color: "var(--c-info)" }}>可前往 <button onClick={() => setView("sessions")}>会话续传</button> 恢复未完成会话。</p>}
      <TranscriptPanel lines={s.transcript} />
    </section>
  );
}
