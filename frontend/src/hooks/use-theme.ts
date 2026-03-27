import { useEffect } from "react";

import { useUiStore } from "@/store/ui-store";

export function useTheme(): void {
  const theme = useUiStore((state) => state.settings.theme);

  useEffect(() => {
    const root = document.documentElement;
    const resolvedTheme =
      theme === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : theme;

    root.classList.toggle("dark", resolvedTheme === "dark");
  }, [theme]);
}
