export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  tags: string[];
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  status: "pending" | "success" | "error";
  metadata?: {
    planning_steps?: PlanStep[] | undefined;
    search_results?: SearchResult[] | undefined;
    generated_files?: FileNode[] | undefined;
    trace?: {
      trace_url?: string | undefined;
      shared_trace_url?: string | undefined;
    } | undefined;
  } | undefined;
}

export interface PlanStep {
  id: string;
  title: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed";
  duration_ms?: number | undefined;
  output?: string | undefined;
}

export interface SearchResult {
  id: string;
  title: string;
  content: string;
  source: "local" | "web" | "skill";
  score: number;
  url?: string | undefined;
}

export interface FileNode {
  name: string;
  path: string;
  type: "file" | "directory";
  status?: "new" | "modified" | "deleted" | undefined;
  size?: number | undefined;
  children?: FileNode[] | undefined;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  keywords: string[];
  usage_count: number;
  last_used: string;
  steps: string[];
}

export interface SessionDetail extends Session {
  messages: Message[];
}

export interface ChatResponse {
  message: Message;
}

export type ChatStreamEvent =
  | { type: "content"; content: string }
  | { type: "planning"; step: PlanStep }
  | { type: "search"; results: SearchResult[] }
  | { type: "file"; file: FileNode }
  | { type: "complete"; summary: string; trace_url?: string; shared_trace_url?: string }
  | { type: "error"; message: string };

export type ContextTab = "planning" | "search" | "files" | "skills";

export interface UiSettings {
  theme: "light" | "dark" | "system";
  language: "zh-CN" | "en-US";
  fontSize: "sm" | "md" | "lg";
  modelName: string;
  temperature: number;
  maxTokens: number;
  apiKey: string;
  searchLimit: number;
  sources: {
    local: boolean;
    web: boolean;
    skill: boolean;
  };
}

export interface ModelOption {
  label: string;
  value: string;
  base_url: string;
}

export interface RuntimeSettings {
  model_name: string;
  ai_base_url: string;
  api_key: string;
  embedding_model_name: string;
  embedding_base_url: string;
  embedding_api_key: string;
  search_limit: number;
  share_public_traces: boolean;
  available_models: ModelOption[];
}

export interface UploadResponse {
  saved_files: string[];
}
