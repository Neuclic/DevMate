"""Tests for the deepagents runtime skeleton."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from devmate.config_loader import load_settings
from devmate.deepagents_runtime import DeepAgentsRuntime
from devmate.mcp_client import SearchResponse, SearchResult
from devmate.session_store import SessionStore


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class StubSearchClient:
    """Fake web search client used by the deepagents runtime tests."""

    def search_web(self, query: str, *, max_results: int = 5) -> SearchResponse:
        del query, max_results
        return SearchResponse(
            query="test",
            results=[
                SearchResult(
                    title="Example Search Result",
                    url="https://example.com",
                    snippet="External guidance",
                )
            ],
        )


class FakeCompiledAgent:
    """Minimal fake compiled graph returned by create_deep_agent."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        del payload
        (self.root_dir / "index.html").write_text(
            "<!DOCTYPE html><title>Deep Agent</title>",
            encoding="utf-8",
        )
        (self.root_dir / "css").mkdir(exist_ok=True)
        (self.root_dir / "css" / "style.css").write_text(
            "body { font-family: sans-serif; }",
            encoding="utf-8",
        )
        return {
            "messages": [
                type("FakeMessage", (), {"content": "Created index.html and css/style.css"})()
            ]
        }

    def stream(self, payload: dict[str, object], stream_mode: str = "updates"):
        del payload, stream_mode
        yield {
            "model": {
                "messages": [
                    SimpleNamespace(
                        content="",
                        tool_calls=[
                            {
                                "name": "write_file",
                                "args": {"file_path": "/index.html", "content": "<!DOCTYPE html>"},
                                "id": "tool-1",
                            }
                        ],
                    )
                ]
            }
        }
        (self.root_dir / "index.html").write_text(
            "<!DOCTYPE html><title>Deep Agent</title>",
            encoding="utf-8",
        )
        yield {
            "tools": {
                "messages": [
                    SimpleNamespace(
                        name="write_file",
                        tool_call_id="tool-1",
                        content="Updated file /index.html",
                    )
                ]
            }
        }
        yield {
            "model": {
                "messages": [
                    SimpleNamespace(
                        content="",
                        tool_calls=[
                            {
                                "name": "run_command",
                                "args": {"command": "npm test"},
                                "id": "tool-2",
                            }
                        ],
                    )
                ]
            }
        }
        yield {
            "tools": {
                "messages": [
                    SimpleNamespace(
                        name="run_command",
                        tool_call_id="tool-2",
                        content="exit_code=0\nok",
                    )
                ]
            }
        }
        if (self.root_dir / "obsolete.txt").exists():
            yield {
                "model": {
                    "messages": [
                        SimpleNamespace(
                            content="",
                            tool_calls=[
                                {
                                    "name": "delete_file",
                                    "args": {"file_path": "/obsolete.txt"},
                                    "id": "tool-3",
                                }
                            ],
                        )
                    ]
                }
            }
            (self.root_dir / "obsolete.txt").unlink()
            yield {
                "tools": {
                    "messages": [
                        SimpleNamespace(
                            name="delete_file",
                            tool_call_id="tool-3",
                            content="Deleted file /obsolete.txt",
                        )
                    ]
                }
            }
        (self.root_dir / "css").mkdir(exist_ok=True)
        (self.root_dir / "css" / "style.css").write_text(
            "body { font-family: sans-serif; }",
            encoding="utf-8",
        )
        yield {
            "model": {
                "messages": [
                    SimpleNamespace(
                        content="Created index.html and css/style.css",
                        tool_calls=[],
                    )
                ]
            }
        }


class DeepAgentsRuntimeHarness(DeepAgentsRuntime):
    """Runtime subclass that injects a fake deep agent."""

    def _build_agent(self, *, prompt: str, workspace_root: Path, target_root: Path, target_root_virtual: str, tracked):  # type: ignore[override]
        del prompt, workspace_root, target_root_virtual
        tracked.retrieved_sources = ["guide.md"]
        tracked.matched_skills = ["build-static-site"]
        tracked.web_results = [
            SearchResult(
                title="Example Search Result",
                url="https://example.com",
                snippet="External guidance",
            )
        ]
        tracked.web_search_attempted = True
        return FakeCompiledAgent(target_root)


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
                'api_key = "test-key"',
                'model_name = "MiniMax-M2"',
                'embedding_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"',
                'embedding_api_key = "embedding-key"',
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
                f'persist_directory = "{(docs_dir.parent / ".chroma" / "test-deepagents").as_posix()}"',
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


def test_deepagents_runtime_detects_written_files() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        (docs_dir / "guide.md").write_text("Local knowledge", encoding="utf-8")
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)

        runtime = DeepAgentsRuntimeHarness(
            settings,
            search_client=StubSearchClient(),
            session_store=SessionStore(root / ".sessions"),
        )
        output_dir = root / "out"
        result = runtime.handle_prompt(
            "Create a tiny site.",
            generate_output_dir=output_dir,
            session_id="deepagents-test",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.generated_files == ["css/style.css", "index.html"]
    assert result.generated_created_files == ["css/style.css", "index.html"]
    assert result.generated_deleted_files is None
    assert result.generation_used_model is True
    assert result.agent_error is None
    assert result.web_search_attempted is True


def test_deepagents_runtime_streams_tool_and_file_events() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        (docs_dir / "guide.md").write_text("Local knowledge", encoding="utf-8")
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)

        runtime = DeepAgentsRuntimeHarness(
            settings,
            search_client=StubSearchClient(),
            session_store=SessionStore(root / ".sessions"),
        )
        output_dir = root / "out"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "obsolete.txt").write_text("legacy", encoding="utf-8")
        events = list(
            runtime.stream_prompt(
                "Create a tiny site.",
                generate_output_dir=output_dir,
                session_id="deepagents-stream-test",
            )
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    event_types = [event["type"] for event in events]
    assert "planning" in event_types
    assert "file" in event_types
    assert "content" in event_types
    assert events[-1]["type"] == "complete"
    file_events = [event["file"] for event in events if event["type"] == "file"]
    assert any(file["path"] == "index.html" for file in file_events)
    assert any(file["path"] == "obsolete.txt" and file["status"] == "deleted" for file in file_events)
    planning_outputs = [
        event["step"].get("output", "")
        for event in events
        if event["type"] == "planning" and isinstance(event.get("step"), dict)
    ]
    assert any("exit_code=0" in str(output) for output in planning_outputs)


def test_diff_files_reports_deleted_paths() -> None:
    created, modified, deleted = DeepAgentsRuntime._diff_files(
        {"obsolete.txt": "legacy", "index.html": "old"},
        {"index.html": "new", "js/main.js": "console.log('x');"},
    )

    assert created == ["js/main.js"]
    assert modified == ["index.html"]
    assert deleted == ["obsolete.txt"]


def test_delete_tool_maps_to_deleted_file_event() -> None:
    event = DeepAgentsRuntime._tool_message_to_file_event(
        "delete_file",
        {"file_path": "/src/app.js"},
        before_snapshot={"src/app.js": "console.log('x');"},
    )

    assert event is not None
    assert event["path"] == "src/app.js"
    assert event["status"] == "deleted"


def test_execute_tool_description_is_readable() -> None:
    description = DeepAgentsRuntime._tool_description(
        "execute",
        {"command": "python -m pytest"},
    )

    assert "python -m pytest" in description


def test_run_command_tool_description_is_readable() -> None:
    description = DeepAgentsRuntime._tool_description(
        "run_command",
        {"command": "npm test"},
    )

    assert "npm test" in description


def test_skill_sources_are_relative_to_workspace_root() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)
        settings = load_settings(config_path)
        runtime = DeepAgentsRuntimeHarness(
            settings,
            search_client=StubSearchClient(),
            session_store=SessionStore(root / ".sessions"),
        )
        assert runtime._skills_sources(root) == ["/.skills/"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_virtual_target_path_is_posix_rooted() -> None:
    workspace_root = Path("D:/DevMate").resolve()
    target_root = (workspace_root / "generated-output" / "demo").resolve()

    assert DeepAgentsRuntime._virtual_target_path(workspace_root, target_root) == "/generated-output/demo"
