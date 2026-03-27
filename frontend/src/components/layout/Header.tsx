import { MoonStar, PanelLeftClose, PanelLeftOpen, Settings, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useSessionStore } from "@/store/session-store";
import { useUiStore } from "@/store/ui-store";

export function Header() {
  const sessionSearch = useSessionStore((state) => state.sessionSearch);
  const setSessionSearch = useSessionStore((state) => state.setSessionSearch);
  const sidebarCollapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const toggleContextPanel = useUiStore((state) => state.toggleContextPanel);

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-background/80 px-5 py-4 backdrop-blur">
      <div className="flex items-center gap-3">
        <Button size="icon" variant="ghost" onClick={toggleSidebar}>
          {sidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </Button>
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-brand">
            <Sparkles className="h-4 w-4" />
            DevMate
          </div>
          <h1 className="text-lg font-semibold text-foreground">AI 编程工作台</h1>
        </div>
      </div>

      <div className="hidden max-w-md flex-1 lg:block">
        <Input
          aria-label="Search sessions"
          placeholder="搜索会话标题..."
          value={sessionSearch}
          onChange={(event) => setSessionSearch(event.target.value)}
        />
      </div>

      <div className="flex items-center gap-2">
        <Button size="icon" variant="ghost" onClick={toggleContextPanel}>
          <MoonStar className="h-4 w-4" />
        </Button>
        <Link className="rounded-md px-3 py-2 text-sm font-medium text-foreground transition hover:bg-muted" to="/skills">
          Skills
        </Link>
        <Link className="inline-flex items-center rounded-md px-3 py-2 text-sm font-medium text-foreground transition hover:bg-muted" to="/settings">
          <Settings className="mr-2 h-4 w-4" />
          设置
        </Link>
      </div>
    </header>
  );
}
