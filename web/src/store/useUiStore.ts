import { create } from "zustand";
import type { IntakeSocket } from "../api/ws";

export type View = "login" | "intake" | "expert" | "sessions" | "ops";
export type Theme = "light" | "dark";
export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";

export interface Toast { id: number; text: string }
export interface SoftBreak { usagePercent: number; monthlyQuotaTokens: number }

export interface UiSlice {
  view: View;
  theme: Theme;
  toasts: Toast[];
  softBreak: SoftBreak | null;
  connection: ConnectionState;
  socket: IntakeSocket | null;   // hook 创建的实时连接，页面经此发送（自审修正）
  setView: (v: View) => void;
  toggleTheme: () => void;
  toast: (text: string) => void;
  dismissToast: (id: number) => void;
  pushSoftBreak: (p: SoftBreak) => void;
  clearSoftBreak: () => void;
  setConnection: (s: ConnectionState) => void;
  setSocket: (s: IntakeSocket | null) => void;
  reset: () => void;
}

let toastId = 0;

export const useUiStore = create<UiSlice>((set) => ({
  view: "login", theme: "light", toasts: [], softBreak: null, connection: "closed", socket: null,
  setView: (v: View): void => set({ view: v }),
  toggleTheme: (): void => set((s) => ({ theme: s.theme === "light" ? "dark" : "light" })),
  toast: (text: string): void => set((s) => ({ toasts: [...s.toasts, { id: ++toastId, text }] })),
  dismissToast: (id: number): void => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  pushSoftBreak: (p: SoftBreak): void => set({ softBreak: p }),
  clearSoftBreak: (): void => set({ softBreak: null }),
  setConnection: (s: ConnectionState): void => set({ connection: s }),
  setSocket: (s: IntakeSocket | null): void => set({ socket: s }),
  reset: (): void => set({ view: "login", theme: "light", toasts: [], softBreak: null, connection: "closed", socket: null }),
}));
