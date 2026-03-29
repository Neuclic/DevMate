import {
  type ChatResponse,
  type FileNode,
  type Message,
  type RuntimeSettings,
  type SearchResult,
  type Session,
  type SessionDetail,
  type Skill,
  type UploadResponse,
} from "@/types";
import { generateId } from "@/lib/utils";

const DEFAULT_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  public readonly status: number;

  public constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions extends RequestInit {
  retries?: number;
}

class ApiClient {
  private readonly baseUrl: string;

  public constructor(baseUrl = DEFAULT_API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  public async getSessions(search?: string): Promise<Session[]> {
    const params = new URLSearchParams();
    if (search) {
      params.set("search", search);
    }
    const raw = await this.request<unknown[]>(
      `/api/sessions${params.size > 0 ? `?${params.toString()}` : ""}`,
    );
    return raw.map(normalizeSession).sort((a, b) => {
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
  }

  public async createSession(title: string): Promise<Session> {
    const raw = await this.request<unknown>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    return normalizeSession(raw);
  }

  public async getSessionDetail(sessionId: string): Promise<SessionDetail> {
    const raw = await this.request<unknown>(`/api/sessions/${sessionId}`);
    return normalizeSessionDetail(raw);
  }

  public async deleteSession(sessionId: string): Promise<void> {
    await this.request(`/api/sessions/${sessionId}`, { method: "DELETE" });
  }

  public async getSettings(): Promise<RuntimeSettings> {
    return await this.request<RuntimeSettings>("/api/settings");
  }

  public async updateSettings(payload: Omit<RuntimeSettings, "available_models">): Promise<RuntimeSettings> {
    return await this.request<RuntimeSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  public async uploadDocs(files: File[]): Promise<UploadResponse> {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return await this.multipartRequest<UploadResponse>("/api/uploads/docs", form);
  }

  public async uploadSkills(files: File[], name?: string): Promise<UploadResponse> {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    if (name?.trim()) {
      form.append("name", name.trim());
    }
    return await this.multipartRequest<UploadResponse>("/api/uploads/skills", form);
  }

  public async postChat(
    sessionId: string,
    message: string,
    runtimeMode: "classic" | "deepagents" = "classic",
  ): Promise<ChatResponse> {
    try {
      const raw = await this.request<unknown>("/api/chat", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, message, runtime_mode: runtimeMode }),
      });
      return normalizeChatResponse(raw, sessionId);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 422) {
        throw error;
      }
      const raw = await this.request<unknown>("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          prompt: message,
          runtime_mode: runtimeMode,
          generate: true,
          output_dir: "generated-output",
        }),
      });
      return normalizeLegacyChatResponse(raw, sessionId, message);
    }
  }

  public async getFiles(sessionId: string): Promise<FileNode[]> {
    const raw = await this.request<unknown[]>(`/api/files/${sessionId}`);
    return raw.map(normalizeFileNode);
  }

  public async getFileContent(path: string, sessionId?: string): Promise<string> {
    const params = new URLSearchParams({ path });
    if (sessionId) {
      params.set("session_id", sessionId);
    }
    const raw = await this.request<string>(`/api/files/content?${params.toString()}`);
    return typeof raw === "string" ? raw : "";
  }

  public async getSkills(query?: { search?: string; type?: string }): Promise<Skill[]> {
    const params = new URLSearchParams();
    if (query?.search) {
      params.set("search", query.search);
    }
    if (query?.type) {
      params.set("type", query.type);
    }
    const raw = await this.request<unknown[]>(
      `/api/skills${params.size > 0 ? `?${params.toString()}` : ""}`,
    );
    return raw.map(normalizeSkill);
  }

  public async getSkill(id: string): Promise<Skill> {
    const raw = await this.request<unknown>(`/api/skills/${id}`);
    return normalizeSkill(raw);
  }

  public async deleteSkill(id: string): Promise<void> {
    await this.request(`/api/skills/${id}`, { method: "DELETE" });
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { retries = 3, headers, ...rest } = options;
    const url = `${this.baseUrl}${path}`;

    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        const response = await fetch(url, {
          ...rest,
          headers: {
            "Content-Type": "application/json",
            ...headers,
          },
        });

        if (!response.ok) {
          const message = await extractErrorMessage(response);
          throw new ApiError(message, response.status);
        }

        if (response.status === 204) {
          return undefined as T;
        }

        return (await response.json()) as T;
      } catch (error) {
        if (attempt === retries) {
          throw error;
        }
        await sleep(2 ** attempt * 250);
      }
    }

    throw new ApiError("Unexpected request failure.", 500);
  }

  private async multipartRequest<T>(path: string, body: FormData, retries = 3): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      try {
        const response = await fetch(url, { method: "POST", body });
        if (!response.ok) {
          const message = await extractErrorMessage(response);
          throw new ApiError(message, response.status);
        }
        return (await response.json()) as T;
      } catch (error) {
        if (attempt === retries) {
          throw error;
        }
        await sleep(2 ** attempt * 250);
      }
    }
    throw new ApiError("Unexpected upload failure.", 500);
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as Record<string, unknown>;
    const detail = payload.detail;
    if (typeof detail === "string") {
      return detail;
    }
  } catch {
    return response.statusText || "Request failed.";
  }
  return response.statusText || "Request failed.";
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function normalizeSession(raw: unknown): Session {
  if (!isRecord(raw)) {
    return {
      id: generateId("session"),
      title: "Untitled Session",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      message_count: 0,
      tags: [],
    };
  }

  const id = readString(raw.id) ?? readString(raw.session_id) ?? generateId("session");
  const updatedAt = readString(raw.updated_at) ?? new Date().toISOString();
  return {
    id,
    title: readString(raw.title) ?? "Untitled Session",
    created_at: readString(raw.created_at) ?? updatedAt,
    updated_at: updatedAt,
    message_count: readNumber(raw.message_count) ?? readNumber(raw.turn_count) ?? 0,
    tags: readStringArray(raw.tags),
  };
}

function normalizeSessionDetail(raw: unknown): SessionDetail {
  const session = normalizeSession(raw);
  if (!isRecord(raw)) {
    return { ...session, messages: [] };
  }

  if (Array.isArray(raw.messages)) {
    return {
      ...session,
      messages: raw.messages.map((item) => normalizeMessage(item, session.id)),
    };
  }

  if (Array.isArray(raw.turns)) {
    const messages = raw.turns.flatMap((turn, index) => {
      if (!isRecord(turn)) {
        return [];
      }
      const timestamp = readString(turn.created_at) ?? session.updated_at;
      const turnId = `${session.id}-${index}`;
      return [
        {
          id: `${turnId}-user`,
          session_id: session.id,
          role: "user" as const,
          content: readString(turn.prompt) ?? "",
          timestamp,
          status: "success" as const,
        },
        {
          id: `${turnId}-assistant`,
          session_id: session.id,
          role: "assistant" as const,
          content: readString(turn.assistant_summary) ?? "",
          timestamp,
          status: readString(turn.agent_error) ? ("error" as const) : ("success" as const),
          metadata: {
            planning_steps: normalizeLegacySteps(turn),
            search_results: normalizeLegacySearchResults(turn),
            generated_files: normalizeLegacyGeneratedFiles(turn),
            trace: normalizeTrace(turn),
          },
        },
      ];
    });
    return {
      ...session,
      messages,
    };
  }

  return {
    ...session,
    messages: [],
  };
}

function normalizeMessage(raw: unknown, sessionId: string): Message {
  if (!isRecord(raw)) {
    return {
      id: generateId("message"),
      session_id: sessionId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      status: "success",
    };
  }

  return {
    id: readString(raw.id) ?? generateId("message"),
    session_id: readString(raw.session_id) ?? sessionId,
    role: readRole(raw.role),
    content: readString(raw.content) ?? "",
    timestamp: readString(raw.timestamp) ?? new Date().toISOString(),
    status: readStatus(raw.status),
    metadata: normalizeMetadata(raw.metadata),
  };
}

function normalizeChatResponse(raw: unknown, sessionId: string): ChatResponse {
  if (isRecord(raw) && isRecord(raw.message)) {
    return {
      message: normalizeMessage(raw.message, sessionId),
    };
  }
  return normalizeLegacyChatResponse(raw, sessionId, "");
}

function normalizeLegacyChatResponse(
  raw: unknown,
  sessionId: string,
  userMessage: string,
): ChatResponse {
  const record = isRecord(raw) ? raw : {};
  const summary = readString(record.summary) ?? "Agent completed the request.";
  return {
    message: {
      id: generateId("assistant"),
      session_id: sessionId,
      role: "assistant",
      content: summary,
      timestamp: new Date().toISOString(),
      status: readString(record.agent_error) ? "error" : "success",
      metadata: {
        planning_steps: normalizeLegacySteps(record),
        search_results: normalizeLegacySearchResults(record),
        generated_files: normalizeLegacyGeneratedFiles(record),
        trace: normalizeTrace(record),
      },
    },
  };
}

function normalizeLegacySteps(record: Record<string, unknown>): import("@/types").PlanStep[] {
  const steps = Array.isArray(record.implementation_steps)
    ? record.implementation_steps
    : [];
  return steps.map((step, index) => ({
    id: `step-${index + 1}`,
    title: `Step ${index + 1}`,
    description: typeof step === "string" ? step : "Generated step",
    status: "completed",
  }));
}

function normalizeLegacySearchResults(record: Record<string, unknown>): SearchResult[] {
  const sources = Array.isArray(record.web_results) ? record.web_results : [];
  const webResults: SearchResult[] = sources.map((item, index) => {
    if (!isRecord(item)) {
      return {
        id: `result-${index}`,
        title: `Result ${index + 1}`,
        content: "",
        source: "web" as const,
        score: 0.5,
      };
    }
    return {
      id: `result-${index}`,
      title: readString(item.title) ?? `Result ${index + 1}`,
      content: readString(item.snippet) ?? "",
      source: "web" as const,
      score: readNumber(item.score) ?? 0.5,
      url: readString(item.url),
    };
  });
  const localResults: SearchResult[] = Array.isArray(record.retrieved_sources)
    ? record.retrieved_sources.map((item, index) => ({
        id: `local-${index}`,
        title: typeof item === "string" ? item : `Local Result ${index + 1}`,
        content: "Loaded from the local knowledge base.",
        source: "local" as const,
        score: 0.7,
      }))
    : [];
  const skillResults: SearchResult[] = Array.isArray(record.matched_skills)
    ? record.matched_skills.map((item, index) => ({
        id: `skill-${index}`,
        title: typeof item === "string" ? item : `Skill ${index + 1}`,
        content: "Matched from the saved skills library.",
        source: "skill" as const,
        score: 0.75,
      }))
    : [];
  return [...webResults, ...localResults, ...skillResults];
}

function normalizeLegacyGeneratedFiles(record: Record<string, unknown>): FileNode[] {
  const files = Array.isArray(record.generated_files) ? record.generated_files : [];
  const deletedFiles = Array.isArray(record.generated_deleted_files)
    ? record.generated_deleted_files.filter((item): item is string => typeof item === "string")
    : [];
  return files.map((item) => {
    const path = typeof item === "string" ? item : "unknown";
    return {
      name: path.split("/").pop() ?? path,
      path,
      type: "file",
      status: deletedFiles.includes(path)
        ? "deleted"
        : Array.isArray(record.generated_modified_files) &&
            record.generated_modified_files.includes(path)
          ? "modified"
          : "new",
    };
  });
}

function normalizeMetadata(raw: unknown): Message["metadata"] | undefined {
  if (!isRecord(raw)) {
    return undefined;
  }
  const planningSteps = Array.isArray(raw.planning_steps)
    ? raw.planning_steps.map((item, index) => normalizePlanStep(item, index))
    : undefined;
  const searchResults = Array.isArray(raw.search_results)
    ? raw.search_results.map((item, index) => normalizeSearchResult(item, index))
    : undefined;
  const generatedFiles = Array.isArray(raw.generated_files)
    ? raw.generated_files.map(normalizeFileNode)
    : undefined;
  const trace = normalizeTrace(raw);

  return {
    planning_steps: planningSteps,
    search_results: searchResults,
    generated_files: generatedFiles,
    trace,
  };
}

function normalizeTrace(record: Record<string, unknown>): NonNullable<Message["metadata"]>["trace"] | undefined {
  const traceUrl = readString(record.trace_url);
  const sharedTraceUrl = readString(record.shared_trace_url);
  if (!traceUrl && !sharedTraceUrl) {
    return undefined;
  }
  return {
    trace_url: traceUrl,
    shared_trace_url: sharedTraceUrl,
  };
}

function normalizePlanStep(raw: unknown, index: number): import("@/types").PlanStep {
  if (!isRecord(raw)) {
    return {
      id: `plan-step-${index}`,
      title: `Step ${index + 1}`,
      description: "",
      status: "pending",
    };
  }
  return {
    id: readString(raw.id) ?? `plan-step-${index}`,
    title: readString(raw.title) ?? `Step ${index + 1}`,
    description: readString(raw.description) ?? "",
    status: readPlanStatus(raw.status),
    duration_ms: readNumber(raw.duration_ms),
    output: readString(raw.output),
  };
}

function normalizeSearchResult(raw: unknown, index: number): SearchResult {
  if (!isRecord(raw)) {
    return {
      id: `search-result-${index}`,
      title: "",
      content: "",
      source: "web",
      score: 0,
    };
  }

  return {
    id: readString(raw.id) ?? `search-result-${index}`,
    title: readString(raw.title) ?? "",
    content: readString(raw.content) ?? readString(raw.snippet) ?? "",
    source: readSource(raw.source),
    score: readNumber(raw.score) ?? 0,
    url: readString(raw.url),
  };
}

function normalizeFileNode(raw: unknown): FileNode {
  if (!isRecord(raw)) {
    return {
      name: "unknown",
      path: "unknown",
      type: "file",
    };
  }

  const path = readString(raw.path) ?? "unknown";
  return {
    name: readString(raw.name) ?? path.split("/").pop() ?? path,
    path,
    type: readString(raw.type) === "directory" ? "directory" : "file",
    status: readFileStatus(raw.status),
    size: readNumber(raw.size),
    children: Array.isArray(raw.children)
      ? raw.children.map(normalizeFileNode)
      : undefined,
  };
}

function normalizeSkill(raw: unknown): Skill {
  if (!isRecord(raw)) {
    return {
      id: generateId("skill"),
      name: "Unknown Skill",
      description: "",
      keywords: [],
      usage_count: 0,
      last_used: new Date().toISOString(),
      steps: [],
    };
  }
  return {
    id: readString(raw.id) ?? readString(raw.slug) ?? generateId("skill"),
    name: readString(raw.name) ?? "Unnamed Skill",
    description: readString(raw.description) ?? readString(raw.summary) ?? "",
    keywords: readStringArray(raw.keywords),
    usage_count: readNumber(raw.usage_count) ?? 0,
    last_used: readString(raw.last_used) ?? new Date().toISOString(),
    steps: readStringArray(raw.steps),
  };
}

function readRole(value: unknown): Message["role"] {
  return value === "user" || value === "system" ? value : "assistant";
}

function readStatus(value: unknown): Message["status"] {
  return value === "pending" || value === "error" ? value : "success";
}

function readPlanStatus(value: unknown): import("@/types").PlanStep["status"] {
  return value === "running" || value === "completed" || value === "failed"
    ? value
    : "pending";
}

function readSource(value: unknown): SearchResult["source"] {
  return value === "local" || value === "skill" ? value : "web";
}

function readFileStatus(value: unknown): FileNode["status"] {
  return value === "modified" || value === "deleted" ? value : value === "new" ? "new" : undefined;
}

function readString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function readNumber(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export const apiClient = new ApiClient();



