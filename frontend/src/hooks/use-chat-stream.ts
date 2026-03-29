import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { openChatStream, type ChatStreamConnection } from "@/lib/sse-client";
import { generateId } from "@/lib/utils";
import { useChatStore } from "@/store/chat-store";
import { useUiStore } from "@/store/ui-store";
import type { ChatResponse, Message } from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function buildUserMessage(sessionId: string, content: string): Message {
  return {
    id: generateId("user"),
    session_id: sessionId,
    role: "user",
    content,
    timestamp: new Date().toISOString(),
    status: "success",
  };
}

function buildAssistantPlaceholder(sessionId: string): Message {
  return {
    id: generateId("assistant"),
    session_id: sessionId,
    role: "assistant",
    content: "",
    timestamp: new Date().toISOString(),
    status: "pending",
    metadata: {
      planning_steps: [],
      search_results: [],
      generated_files: [],
    },
  };
}

export function useChatStream() {
  const queryClient = useQueryClient();
  const connectionRef = useRef<ChatStreamConnection | null>(null);
  const runtimeMode = useUiStore((state) => state.settings.runtimeMode);
  const appendMessage = useChatStore((state) => state.appendMessage);
  const appendAssistantContent = useChatStore((state) => state.appendAssistantContent);
  const updateAssistantStatus = useChatStore((state) => state.updateAssistantStatus);
  const upsertPlanningStep = useChatStore((state) => state.upsertPlanningStep);
  const setSearchResults = useChatStore((state) => state.setSearchResults);
  const appendGeneratedFile = useChatStore((state) => state.appendGeneratedFile);
  const setTraceInfo = useChatStore((state) => state.setTraceInfo);
  const setActiveStreamingSessionId = useChatStore((state) => state.setActiveStreamingSessionId);

  const hydrateFromResponse = useCallback(
    (sessionId: string, placeholderId: string, response: ChatResponse) => {
      updateAssistantStatus(sessionId, placeholderId, response.message.status, response.message.content);
      if (response.message.metadata?.planning_steps) {
        for (const step of response.message.metadata.planning_steps) {
          upsertPlanningStep(sessionId, placeholderId, step);
        }
      }
      if (response.message.metadata?.search_results) {
        setSearchResults(sessionId, placeholderId, response.message.metadata.search_results);
      }
      if (response.message.metadata?.generated_files) {
        for (const file of response.message.metadata.generated_files) {
          appendGeneratedFile(sessionId, placeholderId, file);
        }
      }
      if (response.message.metadata?.trace) {
        setTraceInfo(sessionId, placeholderId, response.message.metadata.trace);
      }
    },
    [appendGeneratedFile, setSearchResults, setTraceInfo, updateAssistantStatus, upsertPlanningStep],
  );

  const stop = useCallback(() => {
    connectionRef.current?.close();
    connectionRef.current = null;
    setActiveStreamingSessionId(null);
  }, [setActiveStreamingSessionId]);

  const sendMessage = useCallback(
    async (sessionId: string, content: string) => {
      const userMessage = buildUserMessage(sessionId, content);
      const assistantMessage = buildAssistantPlaceholder(sessionId);
      appendMessage(sessionId, userMessage);
      appendMessage(sessionId, assistantMessage);
      setActiveStreamingSessionId(sessionId);

      let streamDeliveredContent = false;
      let settled = false;

      const runFallback = async (errorMessage?: string) => {
        if (settled) {
          return;
        }
        settled = true;
        try {
          const response = await apiClient.postChat(sessionId, content, runtimeMode);
          hydrateFromResponse(sessionId, assistantMessage.id, response);
        } catch (error) {
          updateAssistantStatus(
            sessionId,
            assistantMessage.id,
            "error",
            error instanceof Error ? error.message : (errorMessage ?? "Request failed."),
          );
        } finally {
          setActiveStreamingSessionId(null);
          await queryClient.invalidateQueries({ queryKey: ["sessions"] });
          await queryClient.invalidateQueries({ queryKey: ["session-detail", sessionId] });
        }
      };

      try {
        connectionRef.current = openChatStream(
          API_BASE_URL,
          sessionId,
          content,
          {
            runtime_mode: runtimeMode,
          },
          {
          onEvent: (event) => {
            if (settled) {
              return;
            }
            switch (event.type) {
              case "content":
                streamDeliveredContent = true;
                appendAssistantContent(sessionId, assistantMessage.id, event.content);
                break;
              case "planning":
                upsertPlanningStep(sessionId, assistantMessage.id, event.step);
                break;
              case "search":
                setSearchResults(sessionId, assistantMessage.id, event.results);
                break;
              case "file":
                appendGeneratedFile(sessionId, assistantMessage.id, event.file);
                break;
              case "complete":
                settled = true;
                if (event.trace_url || event.shared_trace_url) {
                  setTraceInfo(sessionId, assistantMessage.id, {
                    trace_url: event.trace_url,
                    shared_trace_url: event.shared_trace_url,
                  });
                }
                updateAssistantStatus(
                  sessionId,
                  assistantMessage.id,
                  "success",
                  streamDeliveredContent ? undefined : event.summary,
                );
                setActiveStreamingSessionId(null);
                void queryClient.invalidateQueries({ queryKey: ["sessions"] });
                void queryClient.invalidateQueries({ queryKey: ["session-detail", sessionId] });
                break;
              case "error":
                void runFallback(event.message);
                break;
            }
          },
          onError: () => {
            if (!streamDeliveredContent) {
              void runFallback("SSE connection lost.");
              return;
            }
            settled = true;
            updateAssistantStatus(sessionId, assistantMessage.id, "error");
            setActiveStreamingSessionId(null);
          },
          onClose: () => {
            connectionRef.current = null;
          },
          },
        );
      } catch (error) {
        await runFallback(error instanceof Error ? error.message : "Unable to start chat stream.");
      }
    },
    [
      appendAssistantContent,
      appendGeneratedFile,
      appendMessage,
      hydrateFromResponse,
      queryClient,
      setActiveStreamingSessionId,
      setSearchResults,
      setTraceInfo,
      updateAssistantStatus,
      upsertPlanningStep,
      runtimeMode,
    ],
  );

  return {
    sendMessage,
    stop,
  };
}
