import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Skill } from "@/types";

interface SkillCardProps {
  skill: Skill;
  onSelect: (skill: Skill) => void;
}

export function SkillCard({ skill, onSelect }: SkillCardProps) {
  return (
    <button className="text-left" onClick={() => onSelect(skill)} type="button">
      <Card className="h-full transition hover:-translate-y-0.5 hover:border-brand/40">
        <CardHeader>
          <CardTitle>{skill.name}</CardTitle>
          <CardDescription className="line-clamp-2">{skill.description || "No description"}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {skill.keywords.slice(0, 5).map((keyword) => (
              <Badge key={keyword} variant="secondary">{keyword}</Badge>
            ))}
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>使用 {skill.usage_count} 次</span>
            <span>{skill.last_used}</span>
          </div>
        </CardContent>
      </Card>
    </button>
  );
}
