import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ContextTab, UiSettings } from "@/types";

interface UiStore {
  sidebarCollapsed: boolean;
  contextCollapsed: boolean;
  sidebarWidth: number;
  contextWidth: number;
  activeContextTab: ContextTab;
  settings: UiSettings;
  toggleSidebar: () => void;
  toggleContextPanel: () => void;
  setSidebarWidth: (width: number) => void;
  setContextWidth: (width: number) => void;
  setActiveContextTab: (tab: ContextTab) => void;
  updateSettings: (partial: Partial<UiSettings>) => void;
}

const defaultSettings: UiSettings = {
  theme: "system",
  language: "zh-CN",
  fontSize: "md",
  runtimeMode: "classic",
  modelName: "MiniMax-M2",
  temperature: 0.2,
  maxTokens: 4096,
  apiKey: "",
  searchLimit: 5,
  sources: {
    local: true,
    web: true,
    skill: true,
  },
};

export const useUiStore = create<UiStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      contextCollapsed: false,
      sidebarWidth: 280,
      contextWidth: 320,
      activeContextTab: "planning",
      settings: defaultSettings,
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      toggleContextPanel: () =>
        set((state) => ({ contextCollapsed: !state.contextCollapsed })),
      setSidebarWidth: (width) => set({ sidebarWidth: width }),
      setContextWidth: (width) => set({ contextWidth: width }),
      setActiveContextTab: (tab) => set({ activeContextTab: tab }),
      updateSettings: (partial) =>
        set((state) => ({
          settings: {
            ...state.settings,
            ...partial,
            sources: {
              ...state.settings.sources,
              ...partial.sources,
            },
          },
        })),
    }),
    {
      name: "devmate-ui-store",
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        contextCollapsed: state.contextCollapsed,
        sidebarWidth: state.sidebarWidth,
        contextWidth: state.contextWidth,
        activeContextTab: state.activeContextTab,
        settings: state.settings,
      }),
    },
  ),
);
