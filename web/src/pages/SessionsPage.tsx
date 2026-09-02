import { useEffect, useState } from "react";
import { createRestClient } from "../api/rest";
import { useSessionStore } from "../store/useSessionStore";
import { useAuthStore } from "../store/useAuthStore";
import { useUiStore } from "../store/useUiStore";
import type { IntakeSocketLike } from "./IntakePage";

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

interface SessionRow { session_id: string; status: string; updated_at: string }

export function SessionsPage({ socket }: { socket?: IntakeSocketLike | null }): JSX.Element {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [error, setError] = useState("");
  const token = useAuthStore((st) => st.token);
  const setView = useUiStore((st) => st.setView);

  useEffect(() => {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useUiStore.getState().toast("身份过期") });
    rest.get<{ sessions: SessionRow[] }>("/api/v1/intake/sessions")
      .then((r) => setRows(r.sessions))
      .catch((e) => setError(String(e)));
  }, [token]);

  function resume(row: SessionRow): void {
    useSessionStore.getState().setSessionId(row.session_id);
    const live = useUiStore.getState().socket; // 真实连接（自审修正）
    (socket ?? live)?.send("session_resume", row.session_id, { session_id: row.session_id });
    setView("intake");
  }

  return (
    <section>
      <h2>会话续传（断点续传，白皮书 8.4）</h2>
      {error && <p style={{ color: "var(--c-danger)" }}>{error}</p>}
      {rows.length === 0 && !error && <p style={{ fontSize: 13 }}>暂无会话。</p>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {rows.map((r) => (
          // 整行可点击恢复（测试点击会话号文本触发 resume）
          <li key={r.session_id} onClick={() => resume(r)} style={{ border: "1px solid var(--c-border)", borderRadius: "var(--radius)", padding: 8, margin: "8px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>
              <strong>{r.session_id}</strong>
              <span style={{ fontSize: 12, marginLeft: 8, color: "var(--c-info)" }}>{r.status} · {r.updated_at}</span>
            </span>
            <button onClick={(e) => { e.stopPropagation(); resume(r); }}>恢复</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
