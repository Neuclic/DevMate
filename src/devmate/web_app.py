"""Minimal local web UI for DevMate."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import uvicorn

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import AppSettings
from devmate.session_store import SessionStore


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>DevMate UI</title>
  <style>
    :root {
      --bg: #f4efe8;
      --panel: rgba(255, 255, 255, 0.86);
      --ink: #18231f;
      --accent: #22543d;
      --accent-soft: #d9efe3;
      --border: #d7e1dc;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top, #fff8ef 0%, var(--bg) 58%, #e7efe8 100%);
      min-height: 100vh;
    }
    .app {
      display: grid;
      grid-template-columns: 300px 1fr;
      min-height: 100vh;
      gap: 1rem;
      padding: 1rem;
    }
    .panel {
      background: var(--panel);
      border: 1px solid rgba(255,255,255,0.7);
      backdrop-filter: blur(16px);
      border-radius: 22px;
      box-shadow: 0 18px 36px rgba(24,35,31,0.08);
    }
    .sidebar {
      padding: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    .sidebar h1 {
      margin: 0;
      font-size: 1.4rem;
    }
    .sidebar button, .composer button {
      border: 0;
      border-radius: 14px;
      padding: 0.85rem 1rem;
      cursor: pointer;
      font-weight: 600;
      background: var(--accent);
      color: white;
    }
    .sidebar button.secondary, .composer button.secondary {
      background: transparent;
      color: var(--accent);
      border: 1px solid var(--border);
    }
    .session-list {
      display: grid;
      gap: 0.6rem;
      overflow: auto;
    }
    .session-item {
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 0.85rem;
      background: white;
      cursor: pointer;
    }
    .session-item.active {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    .main {
      display: grid;
      grid-template-rows: 1fr auto;
      gap: 1rem;
      min-height: 0;
    }
    .messages {
      padding: 1rem;
      overflow: auto;
      display: grid;
      gap: 0.85rem;
    }
    .turn {
      display: grid;
      gap: 0.55rem;
      padding: 0.95rem;
      border: 1px solid var(--border);
      border-radius: 18px;
      background: white;
    }
    .prompt {
      font-weight: 600;
    }
    .meta {
      color: #5a6c63;
      font-size: 0.92rem;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
    }
    .section-title {
      margin: 0;
      font-size: 0.92rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #5a6c63;
    }
    .chip {
      border-radius: 999px;
      background: #edf5f1;
      color: var(--accent);
      padding: 0.2rem 0.6rem;
      font-size: 0.85rem;
    }
    .chip.secondary {
      background: #f4f1ea;
      color: #6e5a3a;
    }
    .detail-grid {
      display: grid;
      gap: 0.55rem;
    }
    .detail-card {
      border: 1px solid #e3ece7;
      border-radius: 14px;
      padding: 0.8rem;
      background: #f8fbf9;
    }
    .detail-card a {
      color: var(--accent);
      text-decoration: none;
    }
    .detail-card a:hover {
      text-decoration: underline;
    }
    .composer {
      padding: 1rem;
      display: grid;
      gap: 0.75rem;
    }
    textarea, input[type="text"] {
      width: 100%;
      border-radius: 14px;
      border: 1px solid var(--border);
      padding: 0.85rem 0.9rem;
      font: inherit;
      background: white;
    }
    textarea {
      min-height: 120px;
      resize: vertical;
    }
    .controls {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
    }
    .toggle-row {
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      align-items: center;
      color: #405149;
    }
    .actions {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    .empty {
      color: #60746b;
      padding: 1rem;
    }
    code {
      background: #f2f7f4;
      border-radius: 8px;
      padding: 0.1rem 0.4rem;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      background: #f7fbf8;
      border-radius: 14px;
      padding: 0.85rem;
      border: 1px solid #e3ece7;
    }
    @media (max-width: 980px) {
      .app {
        grid-template-columns: 1fr;
      }
      .main {
        min-height: 70vh;
      }
      .controls {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="panel sidebar">
      <div>
        <h1>DevMate UI</h1>
        <p class="meta">Saved sessions live in <code>.sessions/</code>.</p>
      </div>
      <div class="actions">
        <button id="new-session">New Session</button>
        <button id="refresh-sessions" class="secondary">Refresh</button>
      </div>
      <div id="session-list" class="session-list"></div>
    </aside>

    <main class="main">
      <section id="messages" class="panel messages">
        <div class="empty">Create or select a session, then send a prompt.</div>
      </section>

      <section class="panel composer">
        <textarea id="prompt" placeholder="Describe what you want DevMate to do..."></textarea>
        <div class="controls">
          <input id="output-dir" type="text" value="generated-output" placeholder="Output directory when generate is enabled" />
          <input id="save-skill" type="text" placeholder="Optional skill name to save" />
        </div>
        <div class="toggle-row">
          <label><input id="generate" type="checkbox" checked /> Generate files</label>
        </div>
        <div class="actions">
          <button id="send">Send Prompt</button>
        </div>
      </section>
    </main>
  </div>

  <script>
    let currentSessionId = null;

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
      }
      return await response.json();
    }

    function turnCard(turn) {
      const files = (turn.generated_files || turn.planned_files || []).map((file) => `<span class="chip">${file}</span>`).join("");
      const created = (turn.generated_created_files || []).map((file) => `<span class="chip secondary">${file}</span>`).join("");
      const modified = (turn.generated_modified_files || []).map((file) => `<span class="chip secondary">${file}</span>`).join("");
      const skills = (turn.matched_skills || []).map((item) => `<span class="chip">${item}</span>`).join("");
      const sources = (turn.retrieved_sources || []).map((item) => `<span class="chip secondary">${item}</span>`).join("");
      const steps = (turn.implementation_steps || []).map((step) => `<li>${step}</li>`).join("");
      const webResults = (turn.web_results || []).map((item) => `
        <div class="detail-card">
          <div><a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(item.title || item.url || "Untitled result")}</a></div>
          <div class="meta">${escapeHtml(item.snippet || "")}</div>
        </div>
      `).join("");
      return `
        <article class="turn">
          <div class="prompt">User: ${escapeHtml(turn.prompt)}</div>
          <div>${escapeHtml(turn.assistant_summary)}</div>
          <div class="meta">Planning mode: ${turn.agent_used_model ? "llm" : "fallback"}${turn.generation_used_model ? " | generation: llm" : turn.generation_output_dir ? " | generation: template-fallback" : ""}</div>
          ${skills ? `<div><p class="section-title">Matched Skills</p><div class="chips">${skills}</div></div>` : ""}
          ${sources ? `<div><p class="section-title">Local Sources</p><div class="chips">${sources}</div></div>` : ""}
          ${files ? `<div><p class="section-title">Planned / Generated Files</p><div class="chips">${files}</div></div>` : ""}
          ${created ? `<div><p class="section-title">Created Files</p><div class="chips">${created}</div></div>` : ""}
          ${modified ? `<div><p class="section-title">Modified Files</p><div class="chips">${modified}</div></div>` : ""}
          ${steps ? `<ol>${steps}</ol>` : ""}
          ${turn.generation_output_dir ? `<div class="meta">Output dir: <code>${escapeHtml(turn.generation_output_dir)}</code></div>` : ""}
          ${turn.saved_skill_path ? `<div class="meta">Saved skill: <code>${escapeHtml(turn.saved_skill_path)}</code></div>` : ""}
          ${webResults ? `<div><p class="section-title">Web Results</p><div class="detail-grid">${webResults}</div></div>` : ""}
          ${turn.web_search_error ? `<pre>Web search error: ${escapeHtml(turn.web_search_error)}</pre>` : ""}
          ${turn.agent_error ? `<pre>Planning error: ${escapeHtml(turn.agent_error)}</pre>` : ""}
          ${turn.generation_error ? `<pre>Generation error: ${escapeHtml(turn.generation_error)}</pre>` : ""}
        </article>
      `;
    }

    function renderMessages(session) {
      const container = document.getElementById("messages");
      if (!session || !session.turns || session.turns.length === 0) {
        container.innerHTML = `<div class="empty">This session has no turns yet.</div>`;
        return;
      }
      container.innerHTML = session.turns.map(turnCard).join("");
      container.scrollTop = container.scrollHeight;
    }

    function renderSessionList(sessions) {
      const container = document.getElementById("session-list");
      if (!sessions.length) {
        container.innerHTML = `<div class="empty">No sessions yet.</div>`;
        return;
      }
      container.innerHTML = sessions.map((session) => `
        <div class="session-item ${session.session_id === currentSessionId ? "active" : ""}" data-id="${session.session_id}">
          <div><strong>${escapeHtml(session.title)}</strong></div>
          <div class="meta">${session.turn_count} turns</div>
          <div class="meta">${escapeHtml(session.updated_at)}</div>
        </div>
      `).join("");
      container.querySelectorAll(".session-item").forEach((node) => {
        node.addEventListener("click", async () => {
          currentSessionId = node.dataset.id;
          await loadSession(currentSessionId);
          await loadSessions();
        });
      });
    }

    async function loadSessions() {
      const sessions = await fetchJson("/api/sessions");
      renderSessionList(sessions);
      return sessions;
    }

    async function loadSession(sessionId) {
      const session = await fetchJson(`/api/sessions/${sessionId}`);
      renderMessages(session);
      return session;
    }

    async function createSession() {
      const session = await fetchJson("/api/sessions", { method: "POST", body: JSON.stringify({}) });
      currentSessionId = session.session_id;
      await loadSessions();
      renderMessages(session);
      return session;
    }

    async function sendPrompt() {
      const prompt = document.getElementById("prompt").value.trim();
      if (!prompt) {
        return;
      }
      if (!currentSessionId) {
        await createSession();
      }
      const payload = {
        session_id: currentSessionId,
        prompt,
        generate: document.getElementById("generate").checked,
        output_dir: document.getElementById("output-dir").value.trim() || "generated-output",
        save_skill_name: document.getElementById("save-skill").value.trim() || null,
      };
      const response = await fetchJson("/api/chat", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      currentSessionId = response.session_id;
      document.getElementById("prompt").value = "";
      await loadSessions();
      renderMessages(response.session);
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    document.getElementById("new-session").addEventListener("click", async () => {
      await createSession();
    });
    document.getElementById("refresh-sessions").addEventListener("click", async () => {
      await loadSessions();
    });
    document.getElementById("send").addEventListener("click", async () => {
      try {
        await sendPrompt();
      } catch (error) {
        alert(error.message || String(error));
      }
    });

    loadSessions().catch((error) => {
      console.error(error);
    });
  </script>
</body>
</html>
"""


class CreateSessionRequest(BaseModel):
    """Create-session API payload."""

    title: str | None = None


class ChatRequest(BaseModel):
    """Chat API payload."""

    session_id: str | None = None
    prompt: str = Field(min_length=1)
    generate: bool = True
    output_dir: str = "generated-output"
    save_skill_name: str | None = None


def create_app(
    settings: AppSettings,
    *,
    runtime: DevMateRuntime | None = None,
    session_store: SessionStore | None = None,
) -> FastAPI:
    """Create the local DevMate GUI app."""
    store = session_store or SessionStore(Path(".sessions"))
    active_runtime = runtime or DevMateRuntime(settings=settings, session_store=store)
    app = FastAPI(title="DevMate UI")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return HTML_PAGE

    @app.get("/api/sessions")
    async def list_sessions() -> list[dict[str, object]]:
        return [asdict(item) for item in store.list_sessions()]

    @app.post("/api/sessions")
    async def create_session(payload: CreateSessionRequest) -> dict[str, object]:
        record = store.create_session(title=payload.title)
        return asdict(record)

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, object]:
        record = store.get_session(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        return asdict(record)

    @app.post("/api/chat")
    async def chat(payload: ChatRequest) -> dict[str, object]:
        session_id = payload.session_id
        if not session_id:
            session_id = store.create_session().session_id
        result = active_runtime.handle_prompt(
            payload.prompt,
            save_skill_name=payload.save_skill_name,
            generate_output_dir=Path(payload.output_dir) if payload.generate else None,
            session_id=session_id,
        )
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=500, detail="Session was not persisted.")
        return {
            "session_id": session_id,
            "result": asdict(result),
            "session": asdict(session),
        }

    return app


def run_web_app(settings: AppSettings, *, host: str, port: int) -> None:
    """Run the DevMate GUI locally."""
    uvicorn.run(create_app(settings), host=host, port=port)
