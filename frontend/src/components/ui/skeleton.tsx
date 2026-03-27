import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }): JSX.Element {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}
