import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { UploadCloud } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { apiClient } from "@/lib/api-client";
import { useUiStore } from "@/store/ui-store";

const settingsSchema = z.object({
  model_name: z.string().min(1),
  ai_base_url: z.string().url(),
  api_key: z.string(),
  embedding_model_name: z.string(),
  embedding_base_url: z.string().url(),
  embedding_api_key: z.string(),
  search_limit: z.number().min(1).max(20),
  share_public_traces: z.boolean(),
});

type SettingsValues = z.infer<typeof settingsSchema>;

export function SettingsForm() {
  const updateSettings = useUiStore((state) => state.updateSettings);
  const runtimeMode = useUiStore((state) => state.settings.runtimeMode);
  const [docFiles, setDocFiles] = useState<File[]>([]);

  const settingsQuery = useQuery({
    queryKey: ["runtime-settings"],
    queryFn: () => apiClient.getSettings(),
  });

  const form = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      model_name: "MiniMax-M2",
      ai_base_url: "https://api.minimaxi.com/v1",
      api_key: "",
      embedding_model_name: "text-embedding-v4",
      embedding_base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      embedding_api_key: "",
      search_limit: 5,
      share_public_traces: true,
    },
  });

  useEffect(() => {
    if (!settingsQuery.data) {
      return;
    }
    form.reset({
      model_name: settingsQuery.data.model_name,
      ai_base_url: settingsQuery.data.ai_base_url,
      api_key: settingsQuery.data.api_key,
      embedding_model_name: settingsQuery.data.embedding_model_name,
      embedding_base_url: settingsQuery.data.embedding_base_url,
      embedding_api_key: settingsQuery.data.embedding_api_key,
      search_limit: settingsQuery.data.search_limit,
      share_public_traces: settingsQuery.data.share_public_traces,
    });
    updateSettings({
      runtimeMode: settingsQuery.data.runtime_mode ?? "classic",
      modelName: settingsQuery.data.model_name,
      apiKey: settingsQuery.data.api_key,
      searchLimit: settingsQuery.data.search_limit,
    });
  }, [form, settingsQuery.data, updateSettings]);

  const availableModels = useMemo(() => settingsQuery.data?.available_models ?? [], [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (values: SettingsValues) => apiClient.updateSettings(values),
    onSuccess: (data) => {
      updateSettings({
        runtimeMode,
        modelName: data.model_name,
        apiKey: data.api_key,
        searchLimit: data.search_limit,
      });
      toast.success("运行时设置已保存，后续对话会使用新配置。");
      settingsQuery.refetch();
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "保存设置失败");
    },
  });

  const uploadDocsMutation = useMutation({
    mutationFn: (files: File[]) => apiClient.uploadDocs(files),
    onSuccess: (data) => {
      toast.success(`已上传 ${data.saved_files.length} 个本地文档。`);
      setDocFiles([]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "文档上传失败");
    },
  });

  const onSubmit = (values: SettingsValues) => {
    saveMutation.mutate(values);
  };

  const handleModelChange = (value: string) => {
    const model = availableModels.find((item) => item.value === value);
    form.setValue("model_name", value);
    if (model) {
      form.setValue("ai_base_url", model.base_url);
    }
  };

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6">
      <Card>
        <CardHeader>
          <CardTitle>运行时模型设置</CardTitle>
          <CardDescription>这里保存的是后端实际生效的运行时配置，不再只是浏览器本地假数据。</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-6" onSubmit={form.handleSubmit(onSubmit)}>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">执行引擎</label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={runtimeMode}
                  onChange={(event) =>
                    updateSettings({
                      runtimeMode:
                        event.target.value === "deepagents" ? "deepagents" : "classic",
                    })
                  }
                >
                  <option value="classic">Classic Runtime</option>
                  <option value="deepagents">DeepAgents Runtime</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">模型</label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={form.watch("model_name")}
                  onChange={(event) => handleModelChange(event.target.value)}
                >
                  {availableModels.map((model) => (
                    <option key={model.value} value={model.value}>
                      {model.label}
                    </option>
                  ))}
                  {!availableModels.some((model) => model.value === form.watch("model_name")) ? (
                    <option value={form.watch("model_name")}>{form.watch("model_name")}</option>
                  ) : null}
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">模型 Base URL</label>
                <Input {...form.register("ai_base_url")} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">主模型 API Key</label>
                <Input type="password" {...form.register("api_key")} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">检索数量</label>
                <Input type="number" {...form.register("search_limit", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Embedding 模型</label>
                <Input {...form.register("embedding_model_name")} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Embedding Base URL</label>
                <Input {...form.register("embedding_base_url")} />
              </div>
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm font-medium">Embedding API Key</label>
                <Input type="password" {...form.register("embedding_api_key")} />
              </div>
            </div>

            <label className="flex items-center justify-between rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
              Trace 默认公开分享
              <Switch
                checked={form.watch("share_public_traces")}
                onCheckedChange={(checked) => form.setValue("share_public_traces", checked)}
              />
            </label>

            <div className="flex justify-end">
              <Button disabled={saveMutation.isPending || settingsQuery.isLoading} type="submit">
                {saveMutation.isPending ? "保存中..." : "保存设置"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>上传本地知识文档</CardTitle>
          <CardDescription>上传的文档会写入后端 docs 目录，后续 RAG 检索会自动看到它们。</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="rounded-xl border border-dashed border-border bg-muted/20 p-4">
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <UploadCloud className="h-4 w-4" />
              支持一次上传多个文件，建议使用 `.md`、`.txt`。
            </div>
            <Input
              className="mt-4"
              multiple
              type="file"
              onChange={(event) => setDocFiles(Array.from(event.target.files ?? []))}
            />
          </div>
          <div className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
            <span>{docFiles.length > 0 ? `已选择 ${docFiles.length} 个文件` : "还没有选择文档"}</span>
            <Button
              disabled={docFiles.length === 0 || uploadDocsMutation.isPending}
              onClick={() => uploadDocsMutation.mutate(docFiles)}
              type="button"
            >
              {uploadDocsMutation.isPending ? "上传中..." : "上传文档"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
