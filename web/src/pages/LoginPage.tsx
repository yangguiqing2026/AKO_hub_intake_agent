import { useState } from "react";
import { createRestClient } from "../api/rest";
import { useAuthStore } from "../store/useAuthStore";

const REST_BASE: string = (import.meta.env.VITE_INTAKE_API_URL as string | undefined) ?? "";

interface LoginResult { token: string; expires_at: string; identity: { account: string } }

export function LoginPage(): JSX.Element {
  const [account, setAccount] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const login = useAuthStore((s) => s.login);

  async function submit(): Promise<void> {
    if (!/^\d{6}$/.test(fingerprint)) { setError("指纹须为六位数字"); return; }
    setBusy(true);
    setError("");
    try {
      const rest = createRestClient({ baseUrl: REST_BASE, getToken: () => "", onUnauthorized: () => setError("身份校验失败") });
      const res = await rest.post<LoginResult>("/api/v1/identity/login", { account, fingerprint });
      login(res.token, res.identity.account);
    } catch (e) {
      setError(e instanceof Error ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ maxWidth: 360, margin: "80px auto", textAlign: "center" }}>
      <h1 style={{ color: "var(--c-gold-text)" }}>AKO 工作台</h1>
      <p>登录 AKO 体系（账号 + 六位指纹）</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <input placeholder="账号" value={account} onChange={(e) => setAccount(e.target.value)} style={{ padding: 8 }} />
        <input placeholder="六位指纹" inputMode="numeric" maxLength={6} value={fingerprint} onChange={(e) => setFingerprint(e.target.value.replace(/\D/g, ""))} style={{ padding: 8 }} />
        <button onClick={() => void submit()} disabled={busy || !account}>{busy ? "登录中…" : "登录"}</button>
        {error && <p style={{ color: "var(--c-danger)" }}>{error}</p>}
      </div>
    </section>
  );
}
