import { ChatArea } from "@/components/chat/ChatArea";
import { ContextPanel } from "@/components/layout/ContextPanel";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/store/ui-store";

export function AppShell() {
  const sidebarCollapsed = useUiStore((state) => state.sidebarCollapsed);
  const contextCollapsed = useUiStore((state) => state.contextCollapsed);
  const sidebarWidth = useUiStore((state) => state.sidebarWidth);
  const contextWidth = useUiStore((state) => state.contextWidth);

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <Header />
      <div className="flex min-h-0 flex-1">
        <div
          className={cn(
            "shrink-0 overflow-hidden border-r border-border transition-all duration-200 ease-out",
            sidebarCollapsed && "w-0 border-r-0",
          )}
          style={{ width: sidebarCollapsed ? 0 : sidebarWidth }}
        >
          <Sidebar />
        </div>
        <main className="min-w-0 flex-1">
          <ChatArea />
        </main>
        <div
          className={cn(
            "shrink-0 overflow-hidden border-l border-border transition-all duration-200 ease-out",
            contextCollapsed && "w-0 border-l-0",
          )}
          style={{ width: contextCollapsed ? 0 : contextWidth }}
        >
          <ContextPanel />
        </div>
      </div>
    </div>
  );
}
