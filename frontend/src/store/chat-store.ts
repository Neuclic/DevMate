import { create } from "zustand";

import type { FileNode, Message, PlanStep, SearchResult } from "@/types";

type MessageMap = Record<string, Message[]>;

interface ChatStore {
  messagesBySession: MessageMap;
  activeStreamingSessionId: string | null;
  hydrateMessages: (sessionId: string, messages: Message[]) => void;
  appendMessage: (sessionId: string, message: Message) => void;
  appendAssistantContent: (sessionId: string, messageId: string, chunk: string) => void;
  updateAssistantStatus: (
    sessionId: string,
    messageId: string,
    status: Message["status"],
    content?: string,
  ) => void;
  upsertPlanningStep: (sessionId: string, messageId: string, step: PlanStep) => void;
  setSearchResults: (sessionId: string, messageId: string, results: SearchResult[]) => void;
  appendGeneratedFile: (sessionId: string, messageId: string, file: FileNode) => void;
  setTraceInfo: (
    sessionId: string,
    messageId: string,
    trace: NonNullable<Message["metadata"]>["trace"],
  ) => void;
  setActiveStreamingSessionId: (sessionId: string | null) => void;
}

function updateSessionMessages(
  state: ChatStore,
  sessionId: string,
  updater: (messages: Message[]) => Message[],
): MessageMap {
  return {
    ...state.messagesBySession,
    [sessionId]: updater(state.messagesBySession[sessionId] ?? []),
  };
}

export const useChatStore = create<ChatStore>((set) => ({
  messagesBySession: {},
  activeStreamingSessionId: null,
  hydrateMessages: (sessionId, messages) =>
    set((state) => ({
      messagesBySession: {
        ...state.messagesBySession,
        [sessionId]: messages,
      },
    })),
  appendMessage: (sessionId, message) =>
    set((state) => ({
      messagesBySession: updateSessionMessages(state, sessionId, (messages) => [
        ...messages,
        message,
      ]),
    })),
  appendAssistantContent: (sessionId, messageId, chunk) =>
    set((state) => ({
      messagesBySession: updateSessionMessages(state, sessionId, (messages) =>
        messages.map((message) =>
          message.id === messageId
            ? { ...message, content: `${message.content}${chunk}` }
            : message,
        ),
      ),
    })),
  updateAssistantStatus: (sessionId, messageId, status, content) =>
    set((state) => ({
      messagesBySession: updateSessionMessages(state, sessionId, (messages) =>
        messages.map((message) =>
          message.id === messageId
            ? {
                ...message,
                status,
                content: content ?? message.content,
              }
            : message,
        ),
      ),
    })),
  upsertPlanningStep: (sessionId, messageId, step) =>
    set((state) => ({
      messagesBySession: updateSessionMessages(state, sessionId, (messages) =>
        messages.map((message) => {
          if (message.id !== messageId) {
            return message;
          }
          const existingSteps = message.metadata?.planning_steps ?? [];
          const nextSteps = existingSteps.some((item) => item.id === step.id)
            ? existingSteps.map((item) => (item.id === step.id ? step : item))
            : [...existingSteps, step];
          return {
            ...message,
            metadata: {
              ...message.metadata,
              planning_steps: nextSteps,
            },
          };
        }),
      ),
    })),
  setSearchResults: (sessionId, messageId, results) =>
    set((state) => ({
      messagesBySession: updateSessionMessages(state, sessionId, (messages) =>
        messages.map((message) =>
          message.id === messageId
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  search_results: results,
                },
              }
            : message,
        ),
      ),
    })),
  appendGeneratedFile: (sessionId, messageId, file) =>
    set((state) => ({
      messagesBySession: updateSessionMessages(state, sessionId, (messages) =>
        messages.map((message) => {
          if (message.id !== messageId) {
            return message;
          }
          const existingFiles = message.metadata?.generated_files ?? [];
          return {
            ...message,
            metadata: {
              ...message.metadata,
              generated_files: [...existingFiles, file],
            },
          };
        }),
      ),
    })),
  setTraceInfo: (sessionId, messageId, trace) =>
    set((state) => ({
      messagesBySession: updateSessionMessages(state, sessionId, (messages) =>
        messages.map((message) =>
          message.id === messageId
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  trace,
                },
              }
            : message,
        ),
      ),
    })),
  setActiveStreamingSessionId: (activeStreamingSessionId) => set({ activeStreamingSessionId }),
}));
