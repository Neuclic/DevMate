import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { SettingsForm } from "@/components/settings/SettingsForm";
import { SkillGrid } from "@/components/skills/SkillGrid";

function WorkspaceRoute() {
  return <AppShell />;
}

function SkillsRoute() {
  return (
    <div className="min-h-screen bg-background px-6 py-8 text-foreground">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 pb-6">
        <div>
          <h1 className="text-3xl font-semibold">Skills</h1>
          <p className="mt-1 text-sm text-muted-foreground">查看当前技能库，并验证技能检索是否正常。</p>
        </div>
        <NavLink className="text-sm font-medium text-brand hover:underline" to="/">
          返回工作台
        </NavLink>
      </div>
      <SkillGrid />
    </div>
  );
}

function SettingsRoute() {
  return (
    <div className="min-h-screen bg-background px-6 py-8 text-foreground">
      <div className="mx-auto flex w-full max-w-4xl items-center justify-between gap-4 pb-6">
        <div>
          <h1 className="text-3xl font-semibold">设置</h1>
          <p className="mt-1 text-sm text-muted-foreground">这里的模型、API Key 和知识文档会直接写到后端运行时，而不只是浏览器本地状态。</p>
        </div>
        <NavLink className="text-sm font-medium text-brand hover:underline" to="/">
          返回工作台
        </NavLink>
      </div>
      <SettingsForm />
    </div>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WorkspaceRoute />} />
        <Route path="/skills" element={<SkillsRoute />} />
        <Route path="/settings" element={<SettingsRoute />} />
      </Routes>
    </BrowserRouter>
  );
}
