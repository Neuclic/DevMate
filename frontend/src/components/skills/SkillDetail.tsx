import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import type { Skill } from "@/types";

interface SkillDetailProps {
  skill: Skill | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SkillDetail({ skill, open, onOpenChange }: SkillDetailProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{skill?.name ?? "Skill Detail"}</DialogTitle>
          <DialogDescription>{skill?.description}</DialogDescription>
        </DialogHeader>
        {skill ? (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {skill.keywords.map((keyword) => (
                <Badge key={keyword} variant="secondary">{keyword}</Badge>
              ))}
            </div>
            <div className="grid gap-2 rounded-xl border border-border bg-muted/30 p-4 text-sm">
              <div className="flex items-center justify-between">
                <span>使用次数</span>
                <span>{skill.usage_count}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>最近使用</span>
                <span>{skill.last_used}</span>
              </div>
            </div>
            <ol className="list-decimal space-y-2 pl-5 text-sm text-foreground">
              {skill.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
