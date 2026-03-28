"""Local FastAPI app that powers the DevMate frontend."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
import logging
from pathlib import Path
import re
from typing import Any

from anyio import to_thread
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator
import uvicorn

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import AppSettings
from devmate.observability import latest_trace_info, trace_start_time
from devmate.session_store import SessionRecord, SessionStore, SessionSummary, SessionTurn
from devmate.skill_registry import SkillNote, SkillRegistry

LOGGER = logging.getLogger(__name__)
RUNTIME_STATE_PATH = Path(".runtime") / "ui-settings.json"
AVAILABLE_MODELS = [
    {"label": "MiniMax M2", "value": "MiniMax-M2", "base_url": "https://api.minimaxi.com/v1"},
    {"label": "MiniMax Text 01", "value": "MiniMax-Text-01", "base_url": "https://api.minimaxi.com/v1"},
    {"label": "GPT-4.1 mini", "value": "gpt-4.1-mini", "base_url": "https://api.openai.com/v1"},
    {"label": "GPT-4.1", "value": "gpt-4.1", "base_url": "https://api.openai.com/v1"},
]


HTML_PAGE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>DevMate API</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: 'Segoe UI', sans-serif; background: linear-gradient(180deg, #f8fbff, #edf5ff); color: #0f172a; }
    main { width: min(720px, calc(100vw - 32px)); border-radius: 28px; background: rgba(255,255,255,0.88); padding: 2rem; box-shadow: 0 24px 60px rgba(15,23,42,0.12); }
    code { background: #eff6ff; padding: 0.15rem 0.45rem; border-radius: 8px; }
    a { color: #2563eb; }
  </style>
</head>
<body>
  <main>
    <h1>DevMate backend is running.</h1>
    <p>Use the React frontend at <code>http://127.0.0.1:5173</code> during local development.</p>
    <p>The API base is this server, usually <code>http://127.0.0.1:8765</code>.</p>
  </main>
</body>
</html>
"""


class CreateSessionRequest(BaseModel):
    title: str | None = None


class ChatRequest(BaseModel):
    session_id: str | None = None
    prompt: str | None = None
    message: str | None = None
    generate: bool = True
    output_dir: str | None = None
    save_skill_name: str | None = None

    @model_validator(mode="after")
    def validate_prompt(self) -> "ChatRequest":
        if not (self.prompt or self.message):
            raise ValueError("Either prompt or message is required.")
        return self

    @property
    def effective_prompt(self) -> str:
        return (self.message or self.prompt or "").strip()


class RuntimeSettingsPayload(BaseModel):
    model_name: str = Field(min_length=1)
    ai_base_url: str = Field(min_length=1)
    api_key: str = ""
    embedding_model_name: str = ""
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    search_limit: int = Field(default=5, ge=1, le=20)
    share_public_traces: bool = False


class RuntimeSettingsResponse(RuntimeSettingsPayload):
    available_models: list[dict[str, str]]


def create_app(
    settings: AppSettings,
    *,
    runtime: DevMateRuntime | None = None,
    session_store: SessionStore | None = None,
) -> FastAPI:
    store = session_store or SessionStore(Path(".sessions"))
    initial_settings = _apply_runtime_overrides(settings, _load_runtime_overrides(RUNTIME_STATE_PATH))
    state: dict[str, Any] = {
        "settings": initial_settings,
        "runtime": runtime or DevMateRuntime(settings=initial_settings, session_store=store),
    }
    app = FastAPI(title="DevMate API")

    def current_runtime() -> DevMateRuntime:
        return state["runtime"]

    def current_settings() -> AppSettings:
        return state["settings"]

    def rebuild_runtime(new_settings: AppSettings) -> None:
        state["settings"] = new_settings
        state["runtime"] = DevMateRuntime(settings=new_settings, session_store=store)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return HTML_PAGE

    @app.get("/api/sessions")
    async def list_sessions() -> list[dict[str, object]]:
        return [_session_summary_payload(item) for item in store.list_sessions()]

    @app.post("/api/sessions")
    async def create_session(payload: CreateSessionRequest) -> dict[str, object]:
        record = store.create_session(title=payload.title)
        return _session_summary_payload(_summary_from_record(record))

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, object]:
        record = _get_session_or_404(store, session_id)
        return _session_detail_payload(record)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str) -> None:
        path = store.sessions_dir / f"{session_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Session not found.")
        path.unlink()

    @app.post("/api/chat")
    async def chat(payload: ChatRequest) -> dict[str, object]:
        prompt = payload.effective_prompt
        session_id = payload.session_id or store.create_session().session_id
        started_at = trace_start_time()
        output_dir = _resolve_output_dir(payload.output_dir, session_id)
        result = await to_thread.run_sync(
            lambda: current_runtime().handle_prompt(
                prompt,
                save_skill_name=payload.save_skill_name,
                generate_output_dir=output_dir if payload.generate else None,
                session_id=session_id,
            )
        )
        trace = _resolve_trace_payload(current_settings(), started_at)
        if trace:
            store.update_latest_turn_trace(
                session_id,
                trace_url=trace.get("trace_url"),
                shared_trace_url=trace.get("shared_trace_url"),
            )
        session = _get_session_or_404(store, session_id)
        message = _assistant_message_payload(session_id, session.turns[-1] if session.turns else None)
        return {
            "session_id": session_id,
            "result": asdict(result),
            "message": message,
            "session": _session_detail_payload(session),
            "trace": trace,
        }

    @app.get("/api/chat/stream")
    async def chat_stream(
        session_id: str,
        message: str,
        generate: bool = True,
        output_dir: str | None = None,
        save_skill_name: str | None = None,
    ) -> StreamingResponse:
        def event_stream():
            started_at = trace_start_time()
            pending_complete: dict[str, object] | None = None
            resolved_output_dir = _resolve_output_dir(output_dir, session_id)
            for event in current_runtime().stream_prompt(
                message,
                save_skill_name=save_skill_name,
                generate_output_dir=resolved_output_dir if generate else None,
                session_id=session_id,
            ):
                if event.get("type") == "complete":
                    pending_complete = dict(event)
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if pending_complete is not None:
                trace = _resolve_trace_payload(current_settings(), started_at)
                if trace:
                    store.update_latest_turn_trace(
                        session_id,
                        trace_url=trace.get("trace_url"),
                        shared_trace_url=trace.get("shared_trace_url"),
                    )
                if trace:
                    pending_complete.update(trace)
                yield f"data: {json.dumps(pending_complete, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream; charset=utf-8",
            },
        )

    @app.get("/api/files/content")
    async def get_file_content(
        path: str = Query(...),
        session_id: str | None = Query(None),
    ) -> JSONResponse:
        target = _resolve_file_path(store, path, session_id)
        if target is None or not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
        return JSONResponse(content=target.read_text(encoding="utf-8"))

    @app.get("/api/files/{session_id}")
    async def get_files(session_id: str) -> list[dict[str, object]]:
        record = _get_session_or_404(store, session_id)
        turn = _latest_generation_turn(record)
        if turn is None or not turn.generation_output_dir:
            return []
        output_dir = Path(turn.generation_output_dir)
        if not output_dir.exists():
            return []
        status_map = {path: "new" for path in turn.generated_created_files}
        status_map.update({path: "modified" for path in turn.generated_modified_files})
        files: list[dict[str, object]] = []
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(output_dir).as_posix()
            files.append(
                {
                    "name": path.name,
                    "path": relative,
                    "type": "file",
                    "status": status_map.get(relative),
                    "size": path.stat().st_size,
                }
            )
        return files

    @app.get("/api/settings")
    async def get_settings() -> dict[str, object]:
        return _settings_payload(current_settings())

    @app.put("/api/settings")
    async def update_settings(payload: RuntimeSettingsPayload) -> dict[str, object]:
        overrides = {
            "model_name": payload.model_name,
            "ai_base_url": payload.ai_base_url,
            "api_key": payload.api_key,
            "embedding_model_name": payload.embedding_model_name,
            "embedding_base_url": payload.embedding_base_url,
            "embedding_api_key": payload.embedding_api_key,
            "search_limit": payload.search_limit,
            "share_public_traces": payload.share_public_traces,
        }
        _save_runtime_overrides(RUNTIME_STATE_PATH, overrides)
        new_settings = _apply_runtime_overrides(settings, overrides)
        rebuild_runtime(new_settings)
        return _settings_payload(new_settings)

    @app.post("/api/uploads/docs")
    async def upload_docs(files: list[UploadFile] = File(...)) -> dict[str, object]:
        docs_dir = Path(current_settings().app.docs_dir)
        docs_dir.mkdir(parents=True, exist_ok=True)
        saved_files: list[str] = []
        for upload in files:
            if not upload.filename:
                continue
            filename = Path(upload.filename).name
            target = docs_dir / filename
            content = await upload.read()
            target.write_bytes(content)
            saved_files.append(str(target.resolve()))
        return {"saved_files": saved_files}

    @app.post("/api/uploads/skills")
    async def upload_skills(files: list[UploadFile] = File(...), name: str | None = Form(None)) -> dict[str, object]:
        registry = current_runtime().skill_registry
        saved_files: list[str] = []
        for upload in files:
            if not upload.filename:
                continue
            raw = (await upload.read()).decode("utf-8", errors="ignore")
            note = _skill_note_from_upload(upload.filename, raw, name=name)
            saved_files.append(str(registry.save(note).resolve()))
        return {"saved_files": saved_files}

    @app.get("/api/skills")
    async def list_skills(search: str | None = None, type: str | None = None) -> list[dict[str, object]]:
        del type
        registry = current_runtime().skill_registry
        notes = registry.search(search or "", limit=50) if search else registry.list_skills()
        return [_skill_payload(note) for note in notes]

    @app.get("/api/skills/{skill_id}")
    async def get_skill(skill_id: str) -> dict[str, object]:
        note = current_runtime().skill_registry.load(skill_id)
        if note is None:
            raise HTTPException(status_code=404, detail="Skill not found.")
        return _skill_payload(note)

    @app.delete("/api/skills/{skill_id}", status_code=204)
    async def delete_skill(skill_id: str) -> None:
        note = current_runtime().skill_registry.load(skill_id)
        if note is None or note.source_path is None:
            raise HTTPException(status_code=404, detail="Skill not found.")
        skill_path = Path(note.source_path)
        skill_root = skill_path.parent
        if skill_root.exists() and skill_root.is_dir() and skill_root.name != ".skills":
            for nested in sorted(skill_root.rglob("*"), reverse=True):
                if nested.is_file():
                    nested.unlink()
                elif nested.is_dir():
                    nested.rmdir()
            skill_root.rmdir()

    return app


def _resolve_output_dir(output_dir: str | None, session_id: str) -> Path:
    if output_dir and output_dir.strip():
        return Path(output_dir)
    return Path("generated-output") / session_id


def _get_session_or_404(store: SessionStore, session_id: str) -> SessionRecord:
    record = store.get_session(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return record


def _summary_from_record(record: SessionRecord) -> SessionSummary:
    return SessionSummary(
        session_id=record.session_id,
        title=record.title,
        updated_at=record.updated_at,
        turn_count=len(record.turns),
    )


def _session_summary_payload(item: SessionSummary) -> dict[str, object]:
    return {
        "id": item.session_id,
        "session_id": item.session_id,
        "title": item.title,
        "created_at": item.updated_at,
        "updated_at": item.updated_at,
        "turn_count": item.turn_count,
        "message_count": item.turn_count * 2,
        "tags": [],
    }


def _assistant_message_payload(session_id: str, turn: SessionTurn | None) -> dict[str, object]:
    if turn is None:
        return {
            "id": f"{session_id}-assistant-empty",
            "session_id": session_id,
            "role": "assistant",
            "content": "",
            "timestamp": "",
            "status": "success",
        }
    search_results = [
        {
            "id": f"web-{index}",
            "title": str(item.get("title", "")),
            "content": str(item.get("snippet", "")),
            "source": "web",
            "score": float(item.get("score") or 0.6),
            "url": str(item.get("url", "")) or None,
        }
        for index, item in enumerate(turn.web_results)
    ]
    generated_files = [
        {
            "name": Path(path).name,
            "path": path,
            "type": "file",
            "status": "modified" if path in turn.generated_modified_files else "new",
        }
        for path in turn.generated_files
    ]
    return {
        "id": f"{session_id}-{turn.turn_id}-assistant",
        "session_id": session_id,
        "role": "assistant",
        "content": turn.assistant_summary,
        "timestamp": turn.created_at,
        "status": "error" if turn.agent_error else "success",
        "metadata": {
            "planning_steps": [
                {
                    "id": f"{turn.turn_id}-step-{index}",
                    "title": f"Step {index}",
                    "description": step,
                    "status": "completed",
                }
                for index, step in enumerate(turn.implementation_steps, start=1)
            ],
            "search_results": search_results,
            "generated_files": generated_files,
            "trace": {
                key: value
                for key, value in {
                    "trace_url": turn.trace_url,
                    "shared_trace_url": turn.shared_trace_url,
                }.items()
                if value
            }
            or None,
        },
    }


def _resolve_trace_payload(settings: AppSettings, started_at) -> dict[str, str] | None:
    try:
        trace = latest_trace_info(
            settings,
            started_at=started_at,
            share_public=settings.langsmith.share_public_traces,
        )
    except Exception as exc:
        LOGGER.warning("Unable to resolve LangSmith trace URL: %s", exc)
        return None
    if trace is None:
        return None

    payload: dict[str, str] = {"trace_url": trace.run_url}
    if trace.shared_url:
        payload["shared_trace_url"] = trace.shared_url
    return payload


def _session_detail_payload(record: SessionRecord) -> dict[str, object]:
    messages: list[dict[str, Any]] = []
    for turn in record.turns:
        messages.append(
            {
                "id": f"{record.session_id}-{turn.turn_id}-user",
                "session_id": record.session_id,
                "role": "user",
                "content": turn.prompt,
                "timestamp": turn.created_at,
                "status": "success",
            }
        )
        messages.append(_assistant_message_payload(record.session_id, turn))
    return {
        "id": record.session_id,
        "session_id": record.session_id,
        "title": record.title,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "message_count": len(messages),
        "tags": [],
        "messages": messages,
        "turns": [asdict(turn) for turn in record.turns],
    }


def _latest_generation_turn(record: SessionRecord) -> SessionTurn | None:
    for turn in reversed(record.turns):
        if turn.generation_output_dir or turn.generated_files:
            return turn
    return None


def _resolve_file_path(store: SessionStore, path: str, session_id: str | None) -> Path | None:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if session_id:
        record = store.get_session(session_id)
        if record is None:
            return None
        turn = _latest_generation_turn(record)
        if turn is None or not turn.generation_output_dir:
            return None
        return Path(turn.generation_output_dir) / candidate
    for session in store.list_sessions():
        record = store.get_session(session.session_id)
        if record is None:
            continue
        turn = _latest_generation_turn(record)
        if turn is None or not turn.generation_output_dir:
            continue
        file_path = Path(turn.generation_output_dir) / candidate
        if file_path.exists():
            return file_path
    return None


def _load_runtime_overrides(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning("Unable to read runtime overrides: %s", exc)
        return {}


def _save_runtime_overrides(path: Path, overrides: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _apply_runtime_overrides(settings: AppSettings, overrides: dict[str, object]) -> AppSettings:
    if not overrides:
        return settings
    model = replace(
        settings.model,
        model_name=str(overrides.get("model_name") or settings.model.model_name),
        ai_base_url=str(overrides.get("ai_base_url") or settings.model.ai_base_url),
        api_key=str(overrides.get("api_key") or settings.model.api_key),
        embedding_model_name=str(overrides.get("embedding_model_name") or settings.model.embedding_model_name),
        embedding_base_url=str(overrides.get("embedding_base_url") or settings.model.embedding_base_url),
        embedding_api_key=str(overrides.get("embedding_api_key") or settings.model.embedding_api_key),
    )
    search = replace(
        settings.search,
        default_max_results=int(overrides.get("search_limit") or settings.search.default_max_results),
    )
    langsmith = replace(
        settings.langsmith,
        share_public_traces=bool(overrides.get("share_public_traces", settings.langsmith.share_public_traces)),
    )
    return replace(settings, model=model, search=search, langsmith=langsmith)


def _settings_payload(settings: AppSettings) -> dict[str, object]:
    return {
        "model_name": settings.model.model_name,
        "ai_base_url": settings.model.ai_base_url,
        "api_key": settings.model.api_key,
        "embedding_model_name": settings.model.embedding_model_name,
        "embedding_base_url": settings.model.embedding_base_url,
        "embedding_api_key": settings.model.embedding_api_key,
        "search_limit": settings.search.default_max_results,
        "share_public_traces": settings.langsmith.share_public_traces,
        "available_models": AVAILABLE_MODELS,
    }


def _skill_note_from_upload(filename: str, raw: str, *, name: str | None = None) -> SkillNote:
    stem = Path(filename).stem.replace("-", " ").replace("_", " ").strip() or "Uploaded Skill"
    heading = next((line[2:].strip() for line in raw.splitlines() if line.startswith("# ")), "")
    resolved_name = (name or heading or stem).strip()
    body_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    summary = next(
        (
            line
            for line in body_lines
            if not line.startswith(("#", "-", "*"))
            and not re.match(r"^\d+\.", line)
        ),
        f"Imported from {filename}",
    )
    steps = [
        re.sub(r"^(\d+\.\s*|[-*]\s*)", "", line).strip()
        for line in raw.splitlines()
        if re.match(r"^(\d+\.\s*|[-*]\s+)", line.strip())
    ]
    keywords = [token.lower() for token in re.findall(r"[A-Za-z0-9_]+", resolved_name) if token]
    if not steps:
        steps = ["Review the uploaded skill content and apply it to a matching task."]
    return SkillNote(
        name=resolved_name,
        summary=summary,
        steps=steps[:12],
        keywords=keywords[:8],
        tools=["search_saved_skills", "read_saved_skill"],
    )


def _skill_payload(note: Any) -> dict[str, object]:
    return {
        "id": note.slug or note.name,
        "name": note.name,
        "description": note.summary,
        "keywords": note.keywords,
        "usage_count": 0,
        "last_used": "",
        "steps": note.steps,
    }


def run_web_app(settings: AppSettings, *, host: str, port: int) -> None:
    uvicorn.run(create_app(settings), host=host, port=port)
