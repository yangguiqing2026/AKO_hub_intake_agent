import { useEffect, useRef, useState } from "react";
import { InputComposer } from "../components/InputComposer";
import { ProgressStepper } from "../components/ProgressStepper";
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


  // ── 2026-09-04 投递后轮询执行结果，对话内给出摘要与下载链接 ──
  const [taskResult, setTaskResult] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    const ack = s.hubAck as { ack?: { wo_number?: string } } | null;
    const wo = ack?.ack?.wo_number;
    if (!wo) {
      setTaskResult(null);
      return;
    }
    let cancelled = false;
    let tries = 0;
    const fire = async (): Promise<void> => {
      tries += 1;
      try {
        const resp = await fetch(`${REST_BASE}/api/v1/intake/task/${encodeURIComponent(wo)}/result`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = (await resp.json()) as Record<string, unknown>;
        if (cancelled) return;
        console.info("[result-poll]", tries, resp.status, data.status ?? Object.keys(data));
        if (data.status === "done" || data.status === "failed" || data.status === "not_found") {
          setTaskResult(data);
          window.clearInterval(timer);
          return;
        }
        if (tries >= 15) {
          setTaskResult({ ...data, timeout: true });
          window.clearInterval(timer);
        }
      } catch (e) {
        console.warn("[result-poll] error", tries, e);
        if (tries >= 15) {
          setTaskResult({ error: String(e), timeout: true });
          window.clearInterval(timer);
        }
      }
    };
    const timer = window.setInterval(fire, 3000);
    void fire();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [(s.hubAck as { ack?: { wo_number?: string } } | null)?.ack?.wo_number, token]);

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
  const showResult = !!taskResult && ((taskResult.status === "done" || taskResult.status === "failed" || taskResult.status === "not_found") || taskResult.timeout === true);
  const resultStatus = taskResult ? String(taskResult.status ?? (taskResult.timeout ? "查询超时" : "未知")) : "";
  const resultSummary = taskResult ? String(taskResult.summary ?? "") : "";
  const resultError = taskResult ? String(taskResult.error ?? "") : "";
  const resultTimeout = taskResult?.timeout === true;
  const resultFiles = taskResult && Array.isArray(taskResult.files) ? (taskResult.files as { abs_path?: string }[]) : [];

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
          {s.questions.length > 0 && (
            <div className="c-card" style={{ marginTop: 12 }}>
              {s.questions.map((q) => (
                <p key={q.qid} style={{ margin: "4px 0", whiteSpace: "pre-wrap" }}>
                  助手：{q.text}
                </p>
              ))}
              <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--c-text-sub)" }}>请在下方输入框直接回复</p>
            </div>
          )}
          <DeliveryResultCard hubAck={s.hubAck} queuedLocal={s.queuedLocal} manualReview={s.manualReview} />
          {showResult && (
            <div className="c-card" style={{ marginTop: 12, borderLeft: "3px solid #2e9e5b" }}>
              <h4 style={{ marginTop: 0 }}>执行结果</h4>
              <p style={{ margin: "4px 0" }}>状态：{resultStatus}</p>
              {resultTimeout && <p style={{ margin: "4px 0", color: "#b26a00" }}>结果暂未在对话内取到，请稍后在 AKO 看板任务列表查看。</p>}
              {resultError ? <p style={{ margin: "4px 0", color: "#b00020" }}>查询出错：{resultError}</p> : null}
              {resultSummary ? <p style={{ margin: "4px 0" }}>{resultSummary}</p> : null}
              {resultFiles.map((f, i) => (
                <div key={i} style={{ margin: "4px 0" }}>
                  <a
                    href={`${REST_BASE}/api/v1/intake/download?path=${encodeURIComponent(f.abs_path ?? "")}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "var(--c-accent)" }}
                  >
                    下载结果文件 {i + 1}
                  </a>
                </div>
              ))}
            </div>
          )}
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
