import { cn } from "@/lib/cn";

interface AvatarProps {
  label: string;
  tone?: "brand" | "muted" | "success";
}

export function Avatar({ label, tone = "muted" }: AvatarProps): JSX.Element {
  const toneClass =
    tone === "brand"
      ? "bg-brand/15 text-brand"
      : tone === "success"
        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
        : "bg-muted text-muted-foreground";

  return (
    <span
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold",
        toneClass,
      )}
    >
      {label.slice(0, 2).toUpperCase()}
    </span>
  );
}
