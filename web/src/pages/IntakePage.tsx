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
    // 2026-09-03 修复⑤：澄清态把底部输入当答复走 p0_response，
    // 不再当新 intake_input 空烧 P0 轮次（曾致 P0_MAX_ROUNDS_EXCEEDED 误报）
    if (s.status === "CLARIFYING" && s.questions.length > 0) {
      const first = s.questions[0];
      socketRef.current?.send("p0_response", sid, {
        round: s.round,
        answers: [{ qid: first.qid, value: text }],
      });
      return;
    }
    socketRef.current?.send("intake_input", sid, { text });
  }

  function confirmHuman(): void {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useAuthStore.getState().logout() });
    void rest.post<{ status: string }>("/api/v1/intake/review", {
      session_id: s.sessionId, review_score: s.reviewRecord?.review_score ?? 0, human_confirmed: true,
    }).then(() => setHumanConfirmed(true)).catch((e) => useUiStore.getState().toast(String(e)));
  }

  // 空会话欢迎态（ChatGPT 首页居中问候 + 底部输入）
  const idleEmpty = s.status === "IDLE" && s.transcript.length === 0 && !s.draftWo && s.questions.length === 0
    && !s.reviewRecord && !s.hubAck && !s.queuedLocal && !s.manualReview;

  return (
    <section style={{ display: "flex", flexDirection: "column", flex: "1 1 auto", minHeight: 0 }}>
      {idleEmpty ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", gap: 6, padding: "0 0 24px" }}>
          <p style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>用日常语言描述需求</p>
          <p style={{ margin: 0, fontSize: 14, color: "var(--c-text-sub)" }}>AKO智能系统将自动转发任务给专业agent</p>
        </div>
      ) : (
        <>
          <p style={{ margin: "10px 0 0", fontSize: 12, color: "var(--c-text-sub)" }}>{s.sessionId ? `会话 ${s.sessionId} · ` : ""}状态：{s.status}</p>
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
          <TranscriptPanel lines={s.transcript} />
          {s.status === "IDLE" && !s.draftWo && (
            <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--c-info)" }}>
              可前往 <button onClick={() => setView("sessions")} style={{ padding: "0 2px", fontSize: 13, color: "var(--c-info)", textDecoration: "underline" }}>会话续传</button> 恢复未完成会话。
            </p>
          )}
          <div style={{ flex: 1 }} />
        </>
      )}
      {/* ChatGPT 式底部固定输入 */}
      <div style={{ position: "sticky", bottom: 0, zIndex: 2, paddingTop: 12 }}>
        <InputComposer onSubmit={submit} />
      </div>
    </section>
  );
}
