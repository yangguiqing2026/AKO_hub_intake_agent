import { create } from "zustand";

export type AuthStatus = "logged_out" | "verifying" | "logged_in";

export interface AuthSlice {
  token: string;
  account: string;
  status: AuthStatus;
  login: (token: string, account: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthSlice>((set) => ({
  token: "", account: "", status: "logged_out",
  login: (token: string, account: string): void => set({ token, account, status: "logged_in" }),
  logout: (): void => set({ token: "", account: "", status: "logged_out" }),
}));
