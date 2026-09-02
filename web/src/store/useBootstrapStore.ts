import { create } from "zustand";
import type { BootstrapConfig } from "../schemas/ws";

export interface BootstrapSlice {
  bootstrap: BootstrapConfig | null;
  loaded: boolean;
  setLoaded: (cfg: BootstrapConfig) => void;
  reset: () => void;
}

export const useBootstrapStore = create<BootstrapSlice>((set) => ({
  bootstrap: null,
  loaded: false,
  setLoaded: (cfg: BootstrapConfig): void => set({ bootstrap: cfg, loaded: true }),
  reset: (): void => set({ bootstrap: null, loaded: false }),
}));
