import { create } from "zustand";

interface SessionStore {
  selectedSessionId: string | null;
  sessionSearch: string;
  setSelectedSessionId: (sessionId: string | null) => void;
  setSessionSearch: (value: string) => void;
}

export const useSessionStore = create<SessionStore>((set) => ({
  selectedSessionId: null,
  sessionSearch: "",
  setSelectedSessionId: (selectedSessionId) => set({ selectedSessionId }),
  setSessionSearch: (sessionSearch) => set({ sessionSearch }),
}));
