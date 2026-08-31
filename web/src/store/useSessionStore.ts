import { create } from "zustand";
import type { Question } from "../api/client";

interface SessionState {
  sessionId: string;
  rawText: string;
  status: string;
  questions: Question[];
  previewWo: Record<string, unknown> | null;
  transcript: string[];
  setRawText: (text: string) => void;
  startSession: (sessionId: string) => void;
  setStatus: (status: string) => void;
  setQuestions: (questions: Question[]) => void;
  setPreview: (wo: Record<string, unknown> | null) => void;
  addTranscript: (line: string) => void;
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: "",
  rawText: "",
  status: "IDLE",
  questions: [],
  previewWo: null,
  transcript: [],
  setRawText: (text: string) => set({ rawText: text }),
  startSession: (sessionId: string) => set({ sessionId, status: "PARSING", transcript: [] }),
  setStatus: (status: string) => set({ status }),
  setQuestions: (questions: Question[]) => set({ questions, previewWo: null }),
  setPreview: (wo: Record<string, unknown> | null) => set({ previewWo: wo, questions: [] }),
  addTranscript: (line: string) => set((state) => ({ transcript: [...state.transcript, line] })),
  reset: () => set({ sessionId: "", rawText: "", status: "IDLE", questions: [], previewWo: null, transcript: [] }),
}));

