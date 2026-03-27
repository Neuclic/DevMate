import { useEffect, useMemo, useRef } from "react";

import { MessageBubble } from "@/components/chat/MessageBubble";
import type { Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  streamingMessageId: string | null;
}

export function MessageList({ messages, streamingMessageId }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lastMessageId = useMemo(() => messages.at(-1)?.id ?? null, [messages]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    if (distanceFromBottom < 160) {
      node.scrollTop = node.scrollHeight;
    }
  }, [lastMessageId, messages.length]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5" ref={containerRef}>
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {messages.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border bg-card/70 px-6 py-10 text-center text-sm text-muted-foreground">
            这里会显示完整的对话、规划和生成结果。先在下方输入一条 prompt，我们就能开始联调。
          </div>
        ) : null}
        {messages.map((message) => (
          <MessageBubble
            isStreaming={streamingMessageId === message.id && message.role === "assistant"}
            key={message.id}
            message={message}
          />
        ))}
      </div>
    </div>
  );
}
