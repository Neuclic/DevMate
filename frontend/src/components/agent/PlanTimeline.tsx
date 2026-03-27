import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

import type { PlanStep } from "@/types";

const STATUS_ICON = {
  pending: Circle,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
} as const;

interface PlanTimelineProps {
  steps: PlanStep[];
}

export function PlanTimeline({ steps }: PlanTimelineProps) {
  if (steps.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-3 py-6 text-sm text-muted-foreground">
        规划步骤会在这里实时出现。
      </p>
    );
  }

  return (
    <div className="space-y-3 pt-2">
      {steps.map((step) => {
        const Icon = STATUS_ICON[step.status];
        return (
          <div className="rounded-xl border border-border bg-background p-3" key={step.id}>
            <div className="flex items-start gap-3">
              <Icon className={step.status === "running" ? "mt-0.5 h-4 w-4 animate-spin text-brand" : "mt-0.5 h-4 w-4 text-brand"} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-foreground">{step.title}</p>
                  <span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{step.status}</span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
                {step.output ? <pre className="mt-3 rounded-lg border border-border bg-muted/40 p-3 text-xs text-foreground">{step.output}</pre> : null}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
