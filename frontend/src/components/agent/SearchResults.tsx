import { Badge } from "@/components/ui/badge";
import type { SearchResult } from "@/types";

interface SearchResultsProps {
  results: SearchResult[];
}

const SOURCE_LABEL: Record<SearchResult["source"], string> = {
  local: "本地文档",
  web: "网络搜索",
  skill: "技能匹配",
};

export function SearchResults({ results }: SearchResultsProps) {
  if (results.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-3 py-6 text-sm text-muted-foreground">
        检索结果会在这里出现。
      </p>
    );
  }

  return (
    <div className="space-y-3 pt-2">
      {results.map((result) => (
        <div className="rounded-xl border border-border bg-background p-3" key={result.id}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="font-medium text-foreground">{result.title}</p>
              <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{result.content}</p>
            </div>
            <Badge variant="secondary">{SOURCE_LABEL[result.source]}</Badge>
          </div>
          <div className="mt-3">
            <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
              <span>相关度</span>
              <span>{Math.round(result.score * 100)}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted">
              <div className="h-2 rounded-full bg-brand" style={{ width: `${Math.max(6, result.score * 100)}%` }} />
            </div>
            {result.url ? (
              <a className="mt-3 inline-block text-xs font-medium text-brand hover:underline" href={result.url} rel="noreferrer" target="_blank">
                打开来源
              </a>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
