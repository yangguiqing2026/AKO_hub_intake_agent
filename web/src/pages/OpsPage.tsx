import { useEffect, useState } from "react";
import { createRestClient } from "../api/rest";
import { useAuthStore } from "../store/useAuthStore";
import { useUiStore } from "../store/useUiStore";

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";
const POLL_MS = 10_000;

interface Deps { [name: string]: { ok: boolean; latency_ms?: number } }

export function OpsPage(): JSX.Element {
  const token = useAuthStore((st) => st.token);
  const [health, setHealth] = useState<{ status: string; deps: Deps } | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [queue, setQueue] = useState<{ pending: number; done: number; failed: number } | null>(null);
  const [flushing, setFlushing] = useState(false);

  useEffect(() => {
    const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useAuthStore.getState().logout() });
    let alive = true;
    async function poll(): Promise<void> {
      try {
        const [h, m, q] = await Promise.all([
          rest.get<{ status: string; deps: Deps }>("/health"),
          rest.get<Record<string, unknown>>("/metrics"),
          rest.get<{ pending: number; done: number; failed: number }>("/api/v1/intake/queue/stats"),
        ]);
        if (!alive) return;
        setHealth(h); setMetrics(m); setQueue(q);
      } catch (e) {
        if (alive) useUiStore.getState().toast(`运维面板拉取失败：${String(e)}`);
      }
    }
    void poll();
    const timer = setInterval(() => void poll(), POLL_MS);
    return () => { alive = false; clearInterval(timer); };
  }, [token]);

  async function flush(): Promise<void> {
    setFlushing(true);
    try {
      const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => token, onUnauthorized: () => useAuthStore.getState().logout() });
      const r = await rest.post<{ flushed: string[] }>("/api/v1/intake/queue/flush");
      useUiStore.getState().toast(`已冲刷 ${r.flushed.length} 张工单`);
    } catch (e) {
      useUiStore.getState().toast(`冲刷失败：${String(e)}`);
    } finally {
      setFlushing(false);
    }
  }

  return (
    <section>
      <h2>运维面板</h2>
      <h3>依赖健康</h3>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {health ? Object.entries(health.deps).map(([name, d]) => (
          <li key={name} style={{ margin: "4px 0", fontSize: 14 }}>
            <span style={{ color: d.ok ? "var(--c-success)" : "var(--c-danger)" }}>{d.ok ? "●" : "○"}</span> {name}{d.ok ? "" : "（不可达）"}
          </li>
        )) : <li style={{ fontSize: 13 }}>加载中…</li>}
      </ul>
      <h3>指标（10s 轮询）</h3>
      <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{metrics ? JSON.stringify(metrics, null, 2) : "加载中…"}</pre>
      <h3>本地投递队列</h3>
      {queue ? (
        <p style={{ fontSize: 13 }}>pending {queue.pending} · done {queue.done} · failed {queue.failed}</p>
      ) : <p style={{ fontSize: 13 }}>加载中…</p>}
      <button onClick={() => void flush()} disabled={flushing}>{flushing ? "冲刷中…" : "手动冲刷队列"}</button>
    </section>
  );
}
