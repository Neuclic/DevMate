import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { formatRelativeTime } from "@/lib/utils";
import { useSessions } from "@/hooks/use-sessions";
import { useSessionStore } from "@/store/session-store";

export function Sidebar() {
  const { data: sessions = [], isLoading, createSession, deleteSession } = useSessions();
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId);
  const setSelectedSessionId = useSessionStore((state) => state.setSelectedSessionId);
  const sessionSearch = useSessionStore((state) => state.sessionSearch);
  const setSessionSearch = useSessionStore((state) => state.setSessionSearch);
  const [draftTitle, setDraftTitle] = useState("新的 DevMate 会话");

  return (
    <aside className="flex h-full flex-col border-r border-border bg-card/70">
      <div className="space-y-3 border-b border-border p-4">
        <Button
          className="w-full"
          onClick={() => {
            createSession.mutate(draftTitle, {
              onSuccess: (session) => {
                toast.success(`已创建会话：${session.title}`);
              },
              onError: (error) => {
                toast.error(error instanceof Error ? error.message : "创建会话失败");
              },
            });
          }}
        >
          + 新建会话
        </Button>
        <Input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} />
        <Input
          placeholder="搜索会话..."
          value={sessionSearch}
          onChange={(event) => setSessionSearch(event.target.value)}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <div className="space-y-2">
          {isLoading ? <p className="px-2 text-sm text-muted-foreground">正在加载会话...</p> : null}
          {!isLoading && sessions.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-6 text-sm text-muted-foreground">
              还没有会话。先新建一个，我们就能开始跑完整的 Agent 流程。
            </p>
          ) : null}
          {sessions.map((session) => (
            <div
              className={cn(
                "flex items-start gap-2 rounded-xl border border-border bg-background p-2 transition-colors hover:border-brand/40 hover:bg-muted/60",
                selectedSessionId === session.id && "border-brand bg-brand/5 shadow-sm",
              )}
              key={session.id}
            >
              <button
                className="min-w-0 flex-1 rounded-lg px-2 py-1 text-left"
                onClick={() => setSelectedSessionId(session.id)}
                type="button"
              >
                <p className="truncate font-medium text-foreground">{session.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {session.message_count} 条消息 · {formatRelativeTime(session.updated_at)}
                </p>
              </button>
              <button
                className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-destructive"
                onClick={() => {
                  deleteSession.mutate(session.id, {
                    onSuccess: () => {
                      toast.success("会话已删除");
                    },
                    onError: (error) => {
                      toast.error(error instanceof Error ? error.message : "删除会话失败");
                    },
                  });
                }}
                type="button"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
