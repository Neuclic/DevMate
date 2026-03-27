import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { MessageInput } from "@/components/chat/MessageInput";
import { MessageList } from "@/components/chat/MessageList";
import { apiClient } from "@/lib/api-client";
import { useChatStream } from "@/hooks/use-chat-stream";
import { useChatStore } from "@/store/chat-store";
import { useSessionStore } from "@/store/session-store";
import type { Message } from "@/types";

const EMPTY_MESSAGES: Message[] = [];

export function ChatArea() {
  const queryClient = useQueryClient();
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId);
  const setSelectedSessionId = useSessionStore((state) => state.setSelectedSessionId);
  const hydrateMessages = useChatStore((state) => state.hydrateMessages);
  const messagesBySession = useChatStore((state) => state.messagesBySession);
  const activeStreamingSessionId = useChatStore((state) => state.activeStreamingSessionId);
  const { sendMessage, stop } = useChatStream();
  const [draft, setDraft] = useState("");

  const messages = useMemo(() => {
    if (!selectedSessionId) {
      return EMPTY_MESSAGES;
    }
    return messagesBySession[selectedSessionId] ?? EMPTY_MESSAGES;
  }, [messagesBySession, selectedSessionId]);

  const detailQuery = useQuery({
    queryKey: ["session-detail", selectedSessionId],
    queryFn: () => apiClient.getSessionDetail(selectedSessionId!),
    enabled: Boolean(selectedSessionId),
  });

  useEffect(() => {
    if (selectedSessionId && detailQuery.data) {
      hydrateMessages(selectedSessionId, detailQuery.data.messages);
    }
  }, [detailQuery.data, hydrateMessages, selectedSessionId]);

  const streamingMessageId = useMemo(() => {
    const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");
    return activeStreamingSessionId === selectedSessionId ? (latestAssistant?.id ?? null) : null;
  }, [activeStreamingSessionId, messages, selectedSessionId]);

  const handleSend = async () => {
    const prompt = draft.trim();
    if (!prompt) {
      return;
    }

    let sessionId = selectedSessionId;
    if (!sessionId) {
      try {
        const session = await apiClient.createSession("新的 DevMate 会话");
        sessionId = session.id;
        setSelectedSessionId(sessionId);
        await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "无法创建会话");
        return;
      }
    }

    setDraft("");
    try {
      await sendMessage(sessionId, prompt);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "发送消息失败");
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col">
      <div className="border-b border-border bg-card/40 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Chat Area</p>
            <h2 className="text-xl font-semibold text-foreground">
              {selectedSessionId ? `Session ${selectedSessionId}` : "选择一个会话开始"}
            </h2>
          </div>
          {detailQuery.isFetching ? <span className="text-sm text-muted-foreground">同步会话中...</span> : null}
        </div>
      </div>
      <MessageList messages={messages} streamingMessageId={streamingMessageId} />
      <MessageInput
        isStreaming={activeStreamingSessionId === selectedSessionId}
        onChange={setDraft}
        onSend={() => {
          void handleSend();
        }}
        onStop={stop}
        value={draft}
      />
    </section>
  );
}
