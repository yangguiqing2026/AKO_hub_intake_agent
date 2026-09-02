import { useEffect, useRef } from "react";
import { IntakeSocket } from "../api/ws";
import { useAuthStore } from "../store/useAuthStore";
import { useBootstrapStore } from "../store/useBootstrapStore";
import { useSessionStore } from "../store/useSessionStore";
import { useUiStore } from "../store/useUiStore";

const WS_URL: string = (import.meta.env.VITE_INTAKE_WS_URL as string | undefined) ?? `${location.origin.replace(/^http/, "ws")}/ws/intake`;

export function useIntakeSocket(): void {
  const token = useAuthStore((s) => s.token);
  const socketRef = useRef<IntakeSocket | null>(null);

  useEffect(() => {
    const socket = new IntakeSocket({
      url: WS_URL,
      onOpen: (): void => {
        const t = useAuthStore.getState().token;
        if (t) socket.send("auth", "", { token: t });
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
          useUiStore.getState().toast(`错误 ${msg.payload.code}: ${msg.payload.message}`);
        } else {
          useSessionStore.getState().applyMessage(msg);
        }
      },
      onStateChange: (s): void => useUiStore.getState().setConnection(s),
    });
    socketRef.current = socket;
    useUiStore.getState().setSocket(socket); // 页面经 uiStore.socket 发送（自审修正）
    socket.connect();
    return () => {
      socket.close();
      socketRef.current = null;
      useUiStore.getState().setSocket(null);
    };
  }, [token]);
}
