import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type FallbackProps, ErrorBoundary } from "react-error-boundary";
import { useState } from "react";
import { Toaster } from "sonner";

import { AppRouter } from "@/app/router";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/use-theme";

function ErrorFallback({ resetErrorBoundary }: FallbackProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <div className="max-w-md rounded-xl border border-border bg-card p-6 shadow-floating">
        <h1 className="text-xl font-semibold">界面加载失败</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          前端渲染遇到了未处理错误。先刷新一次，如果还不行我们再看控制台和网络请求。
        </p>
        <div className="mt-4 flex gap-3">
          <Button onClick={() => window.location.reload()}>刷新页面</Button>
          <Button variant="outline" onClick={resetErrorBoundary}>重置边界</Button>
        </div>
      </div>
    </div>
  );
}

export function App() {
  useTheme();

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
          mutations: {
            retry: 0,
          },
        },
      }),
  );

  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <QueryClientProvider client={queryClient}>
        <AppRouter />
        <Toaster position="top-right" richColors />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
