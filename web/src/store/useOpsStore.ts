import { create } from "zustand";

export interface OpsSlice {
  health: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  queueStats: Record<string, number> | null;
  lastFetched: string;
  setHealth: (v: Record<string, unknown>) => void;
  setMetrics: (v: Record<string, unknown>) => void;
  setQueueStats: (v: Record<string, number>) => void;
}

export const useOpsStore = create<OpsSlice>((set) => ({
  health: null, metrics: null, queueStats: null, lastFetched: "",
  setHealth: (v: Record<string, unknown>): void => set({ health: v, lastFetched: new Date().toISOString() }),
  setMetrics: (v: Record<string, unknown>): void => set({ metrics: v, lastFetched: new Date().toISOString() }),
  setQueueStats: (v: Record<string, number>): void => set({ queueStats: v, lastFetched: new Date().toISOString() }),
}));
