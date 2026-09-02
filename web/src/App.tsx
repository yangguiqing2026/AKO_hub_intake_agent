import { useEffect } from "react";
import { LoginPage } from "./pages/LoginPage";
import { IntakePage } from "./pages/IntakePage";
import { ExpertPage } from "./pages/ExpertPage";
import { SessionsPage } from "./pages/SessionsPage";
import { OpsPage } from "./pages/OpsPage";
import { useIntakeSocket } from "./hooks/useIntakeSocket";
import { useAuthStore } from "./store/useAuthStore";
import { useUiStore, type View } from "./store/useUiStore";
import "./styles/tokens.css";

const NAV: { view: View; label: string }[] = [
  { view: "intake", label: "自然语言入口" },
  { view: "expert", label: "专家模式" },
  { view: "sessions", label: "会话续传" },
  { view: "ops", label: "运维面板" },
];

export function App(): JSX.Element {
  useIntakeSocket();
  const loggedIn = useAuthStore((s) => s.status === "logged_in");
  const view = useUiStore((s) => s.view);
  const theme = useUiStore((s) => s.theme);
  const connection = useUiStore((s) => s.connection);
  const softBreak = useUiStore((s) => s.softBreak);
  const setView = useUiStore((s) => s.setView);
  const toggleTheme = useUiStore((s) => s.toggleTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  if (!loggedIn) return <LoginPage />;

  return (
    <div style={{ minHeight: "100vh", background: "var(--c-bg)", color: "var(--c-text)" }}>
      <header style={{ padding: "16px 24px", background: "var(--c-gold-grad)", color: "#fff" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h1 style={{ margin: 0, fontSize: 20 }}>AKO 工厂大门</h1>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span title="连接状态" style={{ width: 10, height: 10, borderRadius: 5, background: connection === "open" ? "#3e7d4f" : connection === "reconnecting" ? "#b8860b" : "#a33a2b" }} />
            <button onClick={toggleTheme}>{theme === "light" ? "深色" : "浅色"}</button>
            <button onClick={() => useAuthStore.getState().logout()}>登出</button>
          </div>
        </div>
        <nav style={{ marginTop: 8, display: "flex", gap: 12 }}>
          {NAV.map((n) => (
            <button key={n.view} onClick={() => setView(n.view)} style={{ fontWeight: view === n.view ? 700 : 400 }}>{n.label}</button>
          ))}
        </nav>
      </header>
      {softBreak && (
        <div style={{ background: "var(--c-warning)", color: "#fff", padding: "8px 24px" }}>
          预算软熔断：用量 {softBreak.usagePercent.toFixed(1)}% / 月配额 {softBreak.monthlyQuotaTokens.toLocaleString()} tokens，已强制专家模式
        </div>
      )}
      {/* 软熔断强制专家模式（设计 4.3/7.6）：仅当用户停在自然语言入口时切换 */}
      <ForceExpertOnSoftBreak active={Boolean(softBreak)} />
      <main style={{ padding: 24, maxWidth: 760, margin: "0 auto" }}>
        {view === "intake" && <IntakePage />}
        {view === "expert" && <ExpertPage />}
        {view === "sessions" && <SessionsPage />}
        {view === "ops" && <OpsPage />}
      </main>
    </div>
  );
}

function ForceExpertOnSoftBreak({ active }: { active: boolean }): null {
  useEffect(() => {
    if (active && useUiStore.getState().view === "intake") {
      useUiStore.getState().setView("expert");
    }
  }, [active]);
  return null;
}
