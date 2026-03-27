import { useMemo } from "react";

import { FileTree } from "@/components/agent/FileTree";
import { PlanTimeline } from "@/components/agent/PlanTimeline";
import { SearchResults } from "@/components/agent/SearchResults";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChatStore } from "@/store/chat-store";
import { useSessionStore } from "@/store/session-store";
import { useUiStore } from "@/store/ui-store";
import type { Message } from "@/types";

const EMPTY_MESSAGES: Message[] = [];

function findLatestAssistantMessage(messages: Message[]): Message | null {
  return [...messages].reverse().find((message) => message.role === "assistant") ?? null;
}

export function ContextPanel() {
  const selectedSessionId = useSessionStore((state) => state.selectedSessionId);
  const messagesBySession = useChatStore((state) => state.messagesBySession);
  const activeTab = useUiStore((state) => state.activeContextTab);
  const setActiveTab = useUiStore((state) => state.setActiveContextTab);

  const messages = useMemo(() => {
    if (!selectedSessionId) {
      return EMPTY_MESSAGES;
    }
    return messagesBySession[selectedSessionId] ?? EMPTY_MESSAGES;
  }, [messagesBySession, selectedSessionId]);

  const latestAssistantMessage = useMemo(() => findLatestAssistantMessage(messages), [messages]);
  const planningSteps = latestAssistantMessage?.metadata?.planning_steps ?? [];
  const searchResults = latestAssistantMessage?.metadata?.search_results ?? [];
  const generatedFiles = latestAssistantMessage?.metadata?.generated_files ?? [];
  const skillResults = searchResults.filter((result) => result.source === "skill");

  return (
    <aside className="flex h-full flex-col bg-card/70">
      <div className="border-b border-border px-4 py-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Context Panel
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          实时查看规划、检索、文件和技能命中。
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden px-4 py-3">
        <Tabs className="flex h-full flex-col" value={activeTab} onValueChange={(value) => setActiveTab(value as typeof activeTab)}>
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="planning">规划</TabsTrigger>
            <TabsTrigger value="search">检索</TabsTrigger>
            <TabsTrigger value="files">文件</TabsTrigger>
            <TabsTrigger value="skills">技能</TabsTrigger>
          </TabsList>
          <TabsContent className="min-h-0 flex-1 overflow-y-auto" value="planning">
            <PlanTimeline steps={planningSteps} />
          </TabsContent>
          <TabsContent className="min-h-0 flex-1 overflow-y-auto" value="search">
            <SearchResults results={searchResults} />
          </TabsContent>
          <TabsContent className="min-h-0 flex-1 overflow-y-auto" value="files">
            <FileTree files={generatedFiles} />
          </TabsContent>
          <TabsContent className="min-h-0 flex-1 overflow-y-auto" value="skills">
            <div className="space-y-3 pt-2">
              {skillResults.length === 0 ? (
                <p className="rounded-xl border border-dashed border-border px-3 py-6 text-sm text-muted-foreground">
                  当前消息里还没有结构化的技能命中结果。后续我们可以把这部分和后端对齐得更完整。
                </p>
              ) : null}
              {skillResults.map((skill) => (
                <div className="rounded-xl border border-border bg-background p-3" key={skill.id}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-foreground">{skill.title}</p>
                    <Badge variant="secondary">{Math.round(skill.score * 100)}%</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{skill.content}</p>
                </div>
              ))}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </aside>
  );
}
