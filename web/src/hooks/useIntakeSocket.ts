import { useEffect } from "react";
import { IntakeSocket } from "../api/ws";
import { useAuthStore } from "../store/useAuthStore";
import { useBootstrapStore } from "../store/useBootstrapStore";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

const WS_URL: string = (import.meta.env.VITE_INTAKE_WS_URL as string | undefined) ?? `${location.origin.replace(/^http/, "ws")}/ws/intake`;

export function useIntakeSocket(): void {
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    const socket = new IntakeSocket({
      url: WS_URL,
      onOpen: (): void => {
        const t = useAuthStore.getState().token;
        if (t) socket.send("auth", "", { token: t });
        // 重连对账（设计 5.4）：已有会话且镜像非空 → resume 拉快照
        const { sessionId, lastSeq } = useSessionStore.getState();
        if (sessionId && lastSeq > 0) socket.send("session_resume", sessionId, { session_id: sessionId });
      },
      onMessage: (msg): void => {
        if (msg.type === "hello") {
          useBootstrapStore.getState().setLoaded(msg.payload.bootstrap);
        } else if (msg.type === "soft_break") {
          // 传输层 payload 为 snake_case（schemas/ws），UiSlice.SoftBreak 为 camelCase，映射后写入。
          useUiStore.getState().pushSoftBreak({
            usagePercent: msg.payload.usage_percent,
            monthlyQuotaTokens: msg.payload.monthly_quota_tokens,
          });
        } else if (msg.type === "error") {
          if (msg.payload.code === "AUTH_REQUIRED") {
            useAuthStore.getState().logout(); // 身份失效 → 回登录（FW-5 合并项）
          } else {
            useUiStore.getState().toast(`错误 ${msg.payload.code}: ${msg.payload.message}`);
          }
        } else {
          useSessionStore.getState().applyMessage(msg);
        }
      },
      onStateChange: (s): void => useUiStore.getState().setConnection(s),
    });
    useUiStore.getState().setSocket(socket); // 页面经 uiStore.socket 发送（自审修正）
    // gap 恢复（设计 3.3）：seq 跳跃 → 发 session_resume
    const onGap = (): void => {
      const { sessionId } = useSessionStore.getState();
      if (sessionId) socket.send("session_resume", sessionId, { session_id: sessionId });
    };
    useSessionStore.getState().setOnGap(onGap);
    socket.connect();
    return () => {
      socket.close();
      useUiStore.getState().setSocket(null);
      useSessionStore.getState().setOnGap(null);
    };
  }, [token]);
}
