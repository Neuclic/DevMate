import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/chat/CodeBlock";
import { StreamCursor } from "@/components/chat/StreamCursor";
import { cn } from "@/lib/cn";
import { formatRelativeTime } from "@/lib/utils";
import type { Message } from "@/types";

interface MessageBubbleProps {
  message: Message;
  isStreaming: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isLong = message.content.length > 500;
  const content = isLong ? `${message.content.slice(0, 200)}...` : message.content;

  return (
    <div className={cn("flex gap-3", isUser && "justify-end")}>
      {!isUser ? <Avatar label="DevMate" tone="brand" /> : null}
      <div
        className={cn(
          "max-w-[78%] rounded-2xl border px-4 py-3 shadow-sm",
          isUser
            ? "border-brand bg-brand text-brand-foreground"
            : "border-border bg-card text-card-foreground",
        )}
      >
        <div className="mb-2 flex items-center gap-2 text-xs opacity-80">
          <Badge variant={message.status === "error" ? "destructive" : "secondary"}>
            {message.status}
          </Badge>
          <span>{formatRelativeTime(message.timestamp)}</span>
        </div>
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown
            rehypePlugins={[rehypeHighlight]}
            remarkPlugins={[remarkGfm]}
            components={{
              code(props) {
                const { children, className, inline } = props as typeof props & { inline?: boolean };
                const match = /language-(\w+)/.exec(className ?? "");
                const rawCode = String(children ?? "").replace(/\n$/, "");
                if (inline) {
                  return <code className="rounded bg-muted px-1 py-0.5">{children}</code>;
                }
                return <CodeBlock code={rawCode} language={match?.[1]} />;
              },
            }}
          >
            {content || (isStreaming ? "" : "(空响应)")}
          </ReactMarkdown>
          {isStreaming ? <StreamCursor /> : null}
        </div>
      </div>
      {isUser ? <Avatar label="你" tone="muted" /> : null}
    </div>
  );
}
