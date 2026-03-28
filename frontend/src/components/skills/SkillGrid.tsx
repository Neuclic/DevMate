import { useMutation } from "@tanstack/react-query";
import { UploadCloud } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { SkillCard } from "@/components/skills/SkillCard";
import { SkillDetail } from "@/components/skills/SkillDetail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api-client";
import { useSkills } from "@/hooks/use-skills";
import type { Skill } from "@/types";

export function SkillGrid() {
  const [search, setSearch] = useState("");
  const [activeSkill, setActiveSkill] = useState<Skill | null>(null);
  const [skillFiles, setSkillFiles] = useState<File[]>([]);
  const [skillName, setSkillName] = useState("");
  const skillsQuery = useSkills(search);

  const skills = useMemo(() => skillsQuery.data ?? [], [skillsQuery.data]);

  const uploadMutation = useMutation({
    mutationFn: () => apiClient.uploadSkills(skillFiles, skillName || undefined),
    onSuccess: (data) => {
      toast.success(`已导入 ${data.saved_files.length} 个 Skill。`);
      setSkillFiles([]);
      setSkillName("");
      skillsQuery.refetch();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Skill 上传失败");
    },
  });

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <div className="grid gap-4 rounded-2xl border border-border bg-card/70 p-4 shadow-sm lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
        <div className="space-y-3">
          <Input
            className="max-w-md"
            placeholder="搜索技能名或关键词..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <p className="text-sm text-muted-foreground">这里既能检索已有技能，也能把你本地的 Skill markdown 直接导入到技能库。</p>
        </div>

        <div className="rounded-xl border border-dashed border-border bg-muted/20 p-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <UploadCloud className="h-4 w-4" />
            导入本地 Skill
          </div>
          <div className="mt-3 grid gap-3">
            <Input
              placeholder="可选：覆盖导入后的 Skill 名称"
              value={skillName}
              onChange={(event) => setSkillName(event.target.value)}
            />
            <Input
              multiple
              type="file"
              onChange={(event) => setSkillFiles(Array.from(event.target.files ?? []))}
            />
            <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
              <span>{skillFiles.length > 0 ? `已选择 ${skillFiles.length} 个文件` : "支持 .md / SKILL.md 文件"}</span>
              <Button
                disabled={skillFiles.length === 0 || uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
                type="button"
              >
                {uploadMutation.isPending ? "导入中..." : "导入 Skill"}
              </Button>
            </div>
          </div>
        </div>
      </div>

      {skillsQuery.isError ? (
        <div className="rounded-2xl border border-dashed border-border bg-card/50 px-6 py-12 text-center text-sm text-muted-foreground">
          技能列表加载失败，先检查后端容器和 `/api/skills` 接口是否正常。
        </div>
      ) : null}

      {!skillsQuery.isError && skills.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-card/50 px-6 py-12 text-center text-sm text-muted-foreground">
          暂无技能。你可以直接在上面导入本地 Skill markdown。
        </div>
      ) : null}

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {skills.map((skill) => (
          <SkillCard key={skill.id} onSelect={setActiveSkill} skill={skill} />
        ))}
      </div>

      <SkillDetail open={activeSkill !== null} onOpenChange={(open) => !open && setActiveSkill(null)} skill={activeSkill} />
    </div>
  );
}
