import { useEffect, useRef, useState } from "react";
import { IntakeSocket, type ServerMessage } from "../api/client";
import { QuestionCard } from "../components/QuestionCard";
import { WoPreviewCard } from "../components/WoPreviewCard";
import { useSessionStore } from "../store/useSessionStore";

export function IntakePage(): JSX.Element {
  const { sessionId, rawText, setRawText, startSession, addTranscript, questions, setQuestions, previewWo, setPreview, status } = useSessionStore();
  const [input, setInput] = useState("");
  const socketRef = useRef<IntakeSocket | null>(null);

  useEffect(() => {
    const socket = new IntakeSocket("ws://localhost:5026/ws/intake", handleMessage);
    socket.connect();
    socketRef.current = socket;
    return () => socket.close();
  }, []);

  function handleMessage(msg: ServerMessage): void {
    if (msg.type === "p0_interrogation") {
      setQuestions(msg.questions);
      addTranscript(`需要澄清 ${msg.questions.length} 项：${msg.questions.map((q) => q.text).join("；")}`);
    } else if (msg.type === "wo_preview") {
      setPreview(msg.draft_wo);
      addTranscript(`工单已生成（置信度 ${msg.confidence_score}），请确认投递。`);
    } else if (msg.type === "status") {
      setQuestions([]);
      setPreview(null);
      addTranscript(`当前状态：${msg.status}`);
    } else {
      addTranscript(`错误：${msg.error}`);
    }
  }

  function submit(): void {
    if (!input.trim()) return;
    const sid = sessionId || `sess-${Date.now()}`;
    startSession(sid);
    addTranscript(`您：${input}`);
    socketRef.current?.send("intake_input", { session_id: sid, text: input });
    setInput("");
  }

  return (
    <section>
      <p>用日常语言描述需求，系统将生成标准 ako1 工单（状态：{status}）。</p>
      <textarea
        rows={4}
        style={{ width: "100%", fontFamily: "inherit" }}
        value={input}
        placeholder="例如：帮我看看报价模块最近的数据有没有问题"
        onChange={(e) => setInput(e.target.value)}
      />
      <button onClick={submit} disabled={!input.trim()}>
        提交
      </button>
      <div style={{ marginTop: 16 }}>
        {questions.length > 0 && <QuestionCard questions={questions} onAnswer={(answers) => socketRef.current?.send("p0_response", { session_id: sessionId, answers })} />}
        {previewWo && <WoPreviewCard wo={previewWo} onConfirm={() => socketRef.current?.send("confirm_deliver", { session_id: sessionId })} />}
        {useSessionStore.getState().transcript.map((line, i) => (
          <p key={i} style={{ fontSize: 14, borderBottom: "1px solid #e5dcc8", padding: 4 }}>
            {line}
          </p>
        ))}
      </div>
    </section>
  );
}

