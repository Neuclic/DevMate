"""Tests for the local FastAPI web app."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from devmate.agent_runtime import PromptResult
from devmate.config_loader import load_settings
from devmate.session_store import SessionStore, SessionTurn
from devmate.skill_registry import SkillRegistry
from devmate.web_app import create_app


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class FakeRuntime:
    """Runtime stub used to exercise the FastAPI layer only."""

    def __init__(self, skill_registry: SkillRegistry) -> None:
        self.skill_registry = skill_registry

    def handle_prompt(self, *args: object, **kwargs: object) -> PromptResult:
        del args, kwargs
        return PromptResult(
            session_id=None,
            summary="Stub summary",
            planned_files=["index.html"],
            implementation_steps=["Do the thing."],
            retrieved_sources=[],
            matched_skills=[],
            web_results=[],
            web_search_attempted=False,
            agent_used_model=False,
        )

    def stream_prompt(self, *args: object, **kwargs: object):
        del args, kwargs
        yield {
            "type": "planning",
            "step": {
                "id": "planning",
                "title": "Draft plan",
                "description": "Planning in progress",
                "status": "running",
            },
        }
        yield {
            "type": "search",
            "results": [
                {
                    "id": "local-guide",
                    "title": "Guide",
                    "content": "Useful local doc",
                    "source": "local",
                    "score": 0.9,
                }
            ],
        }
        yield {
            "type": "file",
            "file": {
                "name": "main.js",
                "path": "js/main.js",
                "type": "file",
                "status": "new",
            },
        }
        yield {"type": "content", "content": "Hello "}
        yield {"type": "content", "content": "world"}
        yield {"type": "complete", "summary": "Completed stream."}


class FakeDeepRuntime(FakeRuntime):
    """Runtime stub for the deepagents route selection tests."""

    def handle_prompt(self, *args: object, **kwargs: object) -> PromptResult:
        del args, kwargs
        return PromptResult(
            session_id=None,
            summary="Deep summary",
            planned_files=["deep.txt"],
            implementation_steps=["Use deepagents."],
            retrieved_sources=[],
            matched_skills=[],
            web_results=[],
            web_search_attempted=False,
            agent_used_model=True,
            generated_files=["deep.txt", "obsolete.txt"],
            generated_created_files=["deep.txt"],
            generated_deleted_files=["obsolete.txt"],
            generation_used_model=True,
        )


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def _write_config(path: Path, *, docs_dir: Path, skills_dir: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[app]",
                'project_name = "DevMate"',
                f'docs_dir = "{docs_dir.as_posix()}"',
                'log_level = "INFO"',
                "",
                "[model]",
                'ai_base_url = "https://api.minimaxi.com/v1"',
                'api_key = "test"',
                'model_name = "MiniMax-M2"',
                'embedding_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"',
                'embedding_api_key = "test"',
                'embedding_model_name = "text-embedding-v4"',
                "",
                "[search]",
                'tavily_api_key = "test"',
                "default_max_results = 5",
                "request_timeout_seconds = 20.0",
                "",
                "[mcp]",
                'server_url = "http://localhost:8001/mcp"',
                'transport = "streamable_http"',
                "tool_timeout_seconds = 30.0",
                "healthcheck_timeout_seconds = 5.0",
                "",
                "[rag]",
                'provider = "chromadb"',
                'collection_name = "devmate-docs"',
                f'persist_directory = "{(docs_dir.parent / ".chroma" / "test-web").as_posix()}"',
                "chunk_size = 400",
                "chunk_overlap = 40",
                "top_k = 4",
                "",
                "[langsmith]",
                "langchain_tracing_v2 = true",
                'langchain_api_key = "test"',
                "",
                "[skills]",
                f'skills_dir = "{skills_dir.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_chat_stream_emits_incremental_events() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        store = SessionStore(root / ".sessions")
        runtime = FakeRuntime(SkillRegistry(skills_dir))
        app = create_app(
            settings,
            runtime=runtime,
            session_store=store,
            runtime_state_path=root / ".runtime" / "ui-settings.json",
        )
        client = TestClient(app)

        session = client.post("/api/sessions", json={"title": "Stream Demo"}).json()
        session_id = session["id"]
        response = client.get(
            "/api/chat/stream",
            params={"session_id": session_id, "message": "stream this"},
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert response.status_code == 200
    events = [
        json.loads(chunk.removeprefix("data: "))
        for chunk in response.text.split("\n\n")
        if chunk.startswith("data: ")
    ]
    assert [event["type"] for event in events] == [
        "planning",
        "search",
        "file",
        "content",
        "content",
        "complete",
    ]
    assert events[-1]["summary"] == "Completed stream."


def test_chat_stream_complete_event_includes_trace_links(monkeypatch) -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        store = SessionStore(root / ".sessions")
        runtime = FakeRuntime(SkillRegistry(skills_dir))
        monkeypatch.setattr(
            "devmate.web_app.latest_trace_info",
            lambda *args, **kwargs: SimpleNamespace(
                run_url="https://smith.langchain.com/public/run",
                shared_url="https://smith.langchain.com/public/share",
            ),
        )
        app = create_app(
            settings,
            runtime=runtime,
            session_store=store,
            runtime_state_path=root / ".runtime" / "ui-settings.json",
        )
        client = TestClient(app)

        session = client.post("/api/sessions", json={"title": "Stream Demo"}).json()
        response = client.get(
            "/api/chat/stream",
            params={"session_id": session["id"], "message": "stream this"},
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    events = [
        json.loads(chunk.removeprefix("data: "))
        for chunk in response.text.split("\n\n")
        if chunk.startswith("data: ")
    ]
    assert events[-1]["type"] == "complete"
    assert events[-1]["trace_url"] == "https://smith.langchain.com/public/run"
    assert events[-1]["shared_trace_url"] == "https://smith.langchain.com/public/share"


def test_chat_response_includes_trace_payload(monkeypatch) -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        store = SessionStore(root / ".sessions")
        runtime = FakeRuntime(SkillRegistry(skills_dir))
        monkeypatch.setattr(
            "devmate.web_app.latest_trace_info",
            lambda *args, **kwargs: SimpleNamespace(
                run_url="https://smith.langchain.com/public/run",
                shared_url="https://smith.langchain.com/public/share",
            ),
        )
        app = create_app(
            settings,
            runtime=runtime,
            session_store=store,
            runtime_state_path=root / ".runtime" / "ui-settings.json",
        )
        client = TestClient(app)

        session = client.post("/api/sessions", json={"title": "Trace Demo"}).json()
        response = client.post(
            "/api/chat",
            json={"session_id": session["id"], "message": "trace this"},
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace"]["trace_url"] == "https://smith.langchain.com/public/run"
    assert payload["trace"]["shared_trace_url"] == "https://smith.langchain.com/public/share"


def test_file_endpoints_return_generated_content() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        store = SessionStore(root / ".sessions")
        runtime = FakeRuntime(SkillRegistry(skills_dir))
        session = store.create_session("Files Demo")
        output_dir = root / "generated-output" / "flappy-demo"
        (output_dir / "js").mkdir(parents=True, exist_ok=True)
        (output_dir / "index.html").write_text("<!DOCTYPE html><title>Game</title>", encoding="utf-8")
        (output_dir / "js" / "main.js").write_text(
            "import { mountFlappyBird } from './game.js';",
            encoding="utf-8",
        )
        store.append_turn(
            session.session_id,
            SessionTurn(
                turn_id="files-demo",
                created_at="2026-03-27T00:00:00+00:00",
                prompt="build a flappy bird web game",
                assistant_summary="Created browser game files.",
                planned_files=["index.html", "js/main.js"],
                implementation_steps=["Create HTML", "Create JS"],
                generation_output_dir=str(output_dir.resolve()),
                generated_files=["index.html", "js/main.js", "obsolete.txt"],
                generated_created_files=["index.html", "js/main.js"],
                generated_deleted_files=["obsolete.txt"],
            ),
        )
        app = create_app(
            settings,
            runtime=runtime,
            session_store=store,
            runtime_state_path=root / ".runtime" / "ui-settings.json",
        )
        client = TestClient(app)

        files_response = client.get(f"/api/files/{session.session_id}")
        content_response = client.get(
            "/api/files/content",
            params={"path": "js/main.js", "session_id": session.session_id},
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert files_response.status_code == 200
    paths = [item["path"] for item in files_response.json()]
    assert paths == ["index.html", "js/main.js"]
    assert content_response.status_code == 200
    assert "mountFlappyBird" in content_response.json()


def test_settings_endpoints_round_trip_runtime_overrides() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        store = SessionStore(root / ".sessions")
        runtime = FakeRuntime(SkillRegistry(skills_dir))
        app = create_app(
            settings,
            runtime=runtime,
            session_store=store,
            runtime_state_path=root / ".runtime" / "ui-settings.json",
        )
        client = TestClient(app)

        get_response = client.get("/api/settings")
        put_response = client.put(
            "/api/settings",
            json={
                "model_name": "gpt-4.1-mini",
                "ai_base_url": "https://api.openai.com/v1",
                "api_key": "runtime-key",
                "embedding_model_name": "text-embedding-v4",
                "embedding_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "embedding_api_key": "embedding-key",
                "search_limit": 7,
                "share_public_traces": True,
            },
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert get_response.status_code == 200
    assert put_response.status_code == 200
    assert put_response.json()["model_name"] == "gpt-4.1-mini"
    assert put_response.json()["search_limit"] == 7


def test_upload_endpoints_save_docs_and_skills() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        store = SessionStore(root / ".sessions")
        runtime = FakeRuntime(SkillRegistry(skills_dir))
        app = create_app(
            settings,
            runtime=runtime,
            session_store=store,
            runtime_state_path=root / ".runtime" / "ui-settings.json",
        )
        client = TestClient(app)

        docs_response = client.post(
            "/api/uploads/docs",
            files=[("files", ("guide.md", b"# Local Guide\n\nUse this doc.", "text/markdown"))],
        )
        skills_response = client.post(
            "/api/uploads/skills",
            files=[("files", ("poster-skill.md", b"# Poster Skill\n\nMake a poster page.\n\n1. Create the layout.", "text/markdown"))],
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert docs_response.status_code == 200
    assert skills_response.status_code == 200
    assert len(docs_response.json()["saved_files"]) == 1
    assert len(skills_response.json()["saved_files"]) == 1


def test_chat_can_switch_to_deepagents_runtime() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        store = SessionStore(root / ".sessions")
        runtime = FakeRuntime(SkillRegistry(skills_dir))
        deep_runtime = FakeDeepRuntime(SkillRegistry(skills_dir))
        app = create_app(
            settings,
            runtime=runtime,
            deepagents_runtime=deep_runtime,
            session_store=store,
            runtime_state_path=root / ".runtime" / "ui-settings.json",
        )
        client = TestClient(app)

        session = client.post("/api/sessions", json={"title": "Deep Demo"}).json()
        response = client.post(
            "/api/chat",
            json={
                "session_id": session["id"],
                "message": "use deepagents",
                "runtime_mode": "deepagents",
            },
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["summary"] == "Deep summary"
    assert payload["result"]["generated_files"] == ["deep.txt", "obsolete.txt"]
    assert payload["result"]["generated_deleted_files"] == ["obsolete.txt"]
