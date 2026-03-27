import { Send, Square } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface MessageInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
}

export function MessageInput({ value, onChange, onSend, onStop, isStreaming }: MessageInputProps) {
  const rows = useMemo(() => Math.min(8, Math.max(2, value.split("\n").length)), [value]);
  const disabled = value.trim().length === 0 && !isStreaming;

  return (
    <div className="border-t border-border bg-card/70 px-6 py-4">
      <div className="mx-auto max-w-4xl rounded-2xl border border-border bg-background p-3 shadow-sm">
        <Textarea
          className="min-h-[80px] resize-none border-0 bg-transparent p-0 shadow-none focus-visible:ring-0"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (isStreaming) {
                onStop();
                return;
              }
              if (value.trim()) {
                onSend();
              }
            }
          }}
          placeholder="告诉 DevMate 你想做什么，例如：build a responsive map website with map sdk best practices"
          rows={rows}
          value={value}
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">{value.length} chars</span>
          <Button disabled={disabled} onClick={isStreaming ? onStop : onSend}>
            {isStreaming ? <Square className="mr-2 h-4 w-4" /> : <Send className="mr-2 h-4 w-4" />}
            {isStreaming ? "停止生成" : "发送"}
          </Button>
        </div>
      </div>
    </div>
  );
}
