import type { ChatStreamEvent } from "@/types";

export interface ChatStreamHandlers {
  onOpen?: () => void;
  onEvent: (event: ChatStreamEvent) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
}

export interface ChatStreamConnection {
  close: () => void;
}

interface StreamParams {
  runtime_mode?: "classic" | "deepagents";
}

export function openChatStream(
  baseUrl: string,
  sessionId: string,
  message: string,
  streamParams: StreamParams,
  handlers: ChatStreamHandlers,
): ChatStreamConnection {
  const params = new URLSearchParams({
    session_id: sessionId,
    message,
  });
  if (streamParams.runtime_mode) {
    params.set("runtime_mode", streamParams.runtime_mode);
  }
  const target = `${baseUrl.replace(/\/$/, "")}/api/chat/stream?${params.toString()}`;
  const source = new EventSource(target);

  source.onopen = () => {
    handlers.onOpen?.();
  };

  source.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as ChatStreamEvent;
      handlers.onEvent(payload);
      if (payload.type === "complete" || payload.type === "error") {
        source.close();
        handlers.onClose?.();
      }
    } catch (error) {
      handlers.onError?.(
        error instanceof Error ? error : new Error("Unable to parse SSE payload."),
      );
    }
  };

  source.onerror = () => {
    source.close();
    handlers.onError?.(new Error("SSE connection lost."));
    handlers.onClose?.();
  };

  return {
    close: () => {
      source.close();
      handlers.onClose?.();
    },
  };
}
