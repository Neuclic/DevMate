import { useMemo, useState } from "react";

import { SkillCard } from "@/components/skills/SkillCard";
import { SkillDetail } from "@/components/skills/SkillDetail";
import { Input } from "@/components/ui/input";
import { useSkills } from "@/hooks/use-skills";
import type { Skill } from "@/types";

export function SkillGrid() {
  const [search, setSearch] = useState("");
  const [activeSkill, setActiveSkill] = useState<Skill | null>(null);
  const skillsQuery = useSkills(search);

  const skills = useMemo(() => skillsQuery.data ?? [], [skillsQuery.data]);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card/70 p-4 shadow-sm md:flex-row md:items-center md:justify-between">
        <Input
          className="max-w-md"
          placeholder="搜索技能名或关键词..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <p className="text-sm text-muted-foreground">当前主要用于验证技能库是否能被检索和展示。</p>
      </div>

      {skillsQuery.isError ? (
        <div className="rounded-2xl border border-dashed border-border bg-card/50 px-6 py-12 text-center text-sm text-muted-foreground">
          当前后端还没暴露完整的 skills REST API，所以这里先优雅降级为空状态。
        </div>
      ) : null}

      {!skillsQuery.isError && skills.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-card/50 px-6 py-12 text-center text-sm text-muted-foreground">
          暂无技能。等我们继续积累更多 Skill 或接上完整技能接口后，这里会变得更丰富。
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
