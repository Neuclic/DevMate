import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useUiStore } from "@/store/ui-store";

const settingsSchema = z.object({
  modelName: z.string().min(1),
  temperature: z.number().min(0).max(2),
  maxTokens: z.number().min(1).max(32000),
  apiKey: z.string(),
  searchLimit: z.number().min(1).max(20),
  local: z.boolean(),
  web: z.boolean(),
  skill: z.boolean(),
});

type SettingsValues = z.infer<typeof settingsSchema>;

export function SettingsForm() {
  const settings = useUiStore((state) => state.settings);
  const updateSettings = useUiStore((state) => state.updateSettings);

  const form = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      modelName: settings.modelName,
      temperature: settings.temperature,
      maxTokens: settings.maxTokens,
      apiKey: settings.apiKey,
      searchLimit: settings.searchLimit,
      local: settings.sources.local,
      web: settings.sources.web,
      skill: settings.sources.skill,
    },
  });

  const onSubmit = (values: SettingsValues) => {
    updateSettings({
      modelName: values.modelName,
      temperature: values.temperature,
      maxTokens: values.maxTokens,
      apiKey: values.apiKey,
      searchLimit: values.searchLimit,
      sources: {
        local: values.local,
        web: values.web,
        skill: values.skill,
      },
    });
    toast.success("设置已保存到本地浏览器");
  };

  return (
    <Card className="mx-auto w-full max-w-4xl">
      <CardHeader>
        <CardTitle>DevMate 设置</CardTitle>
        <CardDescription>这部分先对齐演示所需的核心配置，后面再接更完整的真实后端设置接口。</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-6" onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">模型</label>
              <Input {...form.register("modelName")} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Temperature</label>
              <Input step="0.1" type="number" {...form.register("temperature", { valueAsNumber: true })} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Max Tokens</label>
              <Input type="number" {...form.register("maxTokens", { valueAsNumber: true })} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">检索数量</label>
              <Input type="number" {...form.register("searchLimit", { valueAsNumber: true })} />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">API Key</label>
            <Input type="password" {...form.register("apiKey")} />
          </div>

          <div className="grid gap-3 rounded-xl border border-border bg-muted/30 p-4 md:grid-cols-3">
            <label className="flex items-center justify-between gap-3 text-sm">
              本地检索
              <Switch checked={form.watch("local")} onCheckedChange={(checked) => form.setValue("local", checked)} />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm">
              网络检索
              <Switch checked={form.watch("web")} onCheckedChange={(checked) => form.setValue("web", checked)} />
            </label>
            <label className="flex items-center justify-between gap-3 text-sm">
              技能检索
              <Switch checked={form.watch("skill")} onCheckedChange={(checked) => form.setValue("skill", checked)} />
            </label>
          </div>

          <div className="flex justify-end">
            <Button type="submit">保存设置</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
