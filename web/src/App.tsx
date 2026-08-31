import { useState } from "react";
import { ExpertPage } from "./pages/ExpertPage";
import { IntakePage } from "./pages/IntakePage";

export function App(): JSX.Element {
  const [page, setPage] = useState<"intake" | "expert">("intake");
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", color: "#3d2b1f", minHeight: "100vh", background: "#faf6ef" }}>
      <header style={{ padding: "16px 24px", background: "linear-gradient(90deg,#8a6d3b,#c9a227)", color: "#fff" }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>AKO 工厂大门</h1>
        <nav style={{ marginTop: 8, display: "flex", gap: 12 }}>
          <button onClick={() => setPage("intake")}>自然语言入口</button>
          <button onClick={() => setPage("expert")}>专家模式（ako1 表单）</button>
        </nav>
      </header>
      <main style={{ padding: 24, maxWidth: 760, margin: "0 auto" }}>
        {page === "intake" ? <IntakePage /> : <ExpertPage />}
      </main>
    </div>
  );
}

