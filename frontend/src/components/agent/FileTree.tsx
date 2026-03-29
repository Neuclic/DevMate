import { FileCode2, FolderOpen, Download, Copy } from "lucide-react";
import { lazy, Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { FileNode } from "@/types";

const MonacoEditor = lazy(async () => {
  const mod = await import("@monaco-editor/react");
  return { default: mod.default };
});

interface FileTreeProps {
  files: FileNode[];
  sessionId?: string | null;
}

function buildTree(files: FileNode[]): FileNode[] {
  const root: FileNode[] = [];
  const directories = new Map<string, FileNode>();

  for (const file of files) {
    const parts = file.path.split("/").filter(Boolean);
    if (parts.length <= 1) {
      root.push(file);
      continue;
    }

    let currentPath = "";
    let currentChildren = root;
    for (const [index, part] of parts.entries()) {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLast = index === parts.length - 1;
      if (isLast) {
        currentChildren.push({ ...file, name: part });
        break;
      }
      let directory = directories.get(currentPath);
      if (!directory) {
        directory = {
          name: part,
          path: currentPath,
          type: "directory",
          children: [],
        };
        directories.set(currentPath, directory);
        currentChildren.push(directory);
      }
      currentChildren = directory.children ?? [];
      directory.children = currentChildren;
    }
  }

  return root;
}

function mergeFilesWithDeleted(serverFiles: FileNode[], localFiles: FileNode[]): FileNode[] {
  const merged = new Map<string, FileNode>();
  for (const file of serverFiles) {
    merged.set(file.path, file);
  }
  for (const file of localFiles) {
    const existing = merged.get(file.path);
    if (existing) {
      merged.set(file.path, { ...existing, status: file.status ?? existing.status });
      continue;
    }
    merged.set(file.path, file);
  }
  return Array.from(merged.values()).sort((a, b) => a.path.localeCompare(b.path));
}

function FileNodeItem({ node, onOpen }: { node: FileNode; onOpen: (node: FileNode) => void }) {
  if (node.type === "directory") {
    return (
      <details className="group rounded-lg border border-border/60 bg-background px-3 py-2">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-foreground">
          <FolderOpen className="h-4 w-4 text-brand" />
          {node.name}
        </summary>
        <div className="mt-2 space-y-2 pl-5">
          {(node.children ?? []).map((child) => (
            <FileNodeItem key={child.path} node={child} onOpen={onOpen} />
          ))}
        </div>
      </details>
    );
  }

  const isDeleted = node.status === "deleted";

  return (
    <button
      className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm ${
        isDeleted
          ? "border-destructive/30 bg-destructive/5 text-muted-foreground"
          : "border-border/60 bg-background hover:border-brand/40 hover:bg-muted/50"
      }`}
      onClick={() => {
        if (!isDeleted) {
          onOpen(node);
        }
      }}
      type="button"
    >
      <span className="flex items-center gap-2 truncate">
        <FileCode2 className="h-4 w-4 text-brand" />
        {node.name}
      </span>
      <span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{node.status ?? "file"}</span>
    </button>
  );
}

export function FileTree({ files, sessionId }: FileTreeProps) {
  const serverFilesQuery = useQuery({
    queryKey: ["session-files", sessionId],
    queryFn: () => apiClient.getFiles(sessionId!),
    enabled: Boolean(sessionId),
  });
  const resolvedFiles = useMemo(
    () => mergeFilesWithDeleted(serverFilesQuery.data ?? [], files),
    [serverFilesQuery.data, files],
  );
  const tree = useMemo(() => buildTree(resolvedFiles), [resolvedFiles]);
  const [activeFile, setActiveFile] = useState<FileNode | null>(null);
  const [content, setContent] = useState("文件内容预览将在这里显示。");

  const openFile = async (node: FileNode) => {
    setActiveFile(node);
    try {
      const value = await apiClient.getFileContent(node.path, sessionId ?? undefined);
      setContent(value || `后端返回了空内容：${node.path}`);
    } catch {
      setContent(`当前后端没有返回 ${node.path} 的文件内容。`);
    }
  };

  if (resolvedFiles.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-3 py-6 text-sm text-muted-foreground">
        生成或修改文件后，这里会展示树形结构。
      </p>
    );
  }

  return (
    <>
      <div className="space-y-2 pt-2">
        {tree.map((node) => (
          <FileNodeItem key={node.path} node={node} onOpen={openFile} />
        ))}
      </div>

      <Dialog open={activeFile !== null} onOpenChange={(open) => !open && setActiveFile(null)}>
        <DialogContent className="max-h-[85vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle>{activeFile?.name ?? "文件预览"}</DialogTitle>
            <DialogDescription>{activeFile?.path}</DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={async () => {
                await navigator.clipboard.writeText(content);
              }}
            >
              <Copy className="mr-2 h-4 w-4" />复制全部
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = activeFile?.name ?? "devmate-file.txt";
                link.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download className="mr-2 h-4 w-4" />下载
            </Button>
          </div>
          <div className="min-h-[420px] overflow-hidden rounded-xl border border-border">
            <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">正在加载编辑器...</div>}>
              <MonacoEditor
                height="420px"
                language={activeFile?.name.split(".").pop() ?? "text"}
                options={{ readOnly: true, minimap: { enabled: false } }}
                theme="vs-dark"
                value={content}
              />
            </Suspense>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
