"""Tests for prompt-time MCP search integration."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import load_settings
from devmate.mcp_client import SearchResponse, SearchResult
from devmate.planning_agent import AgentPlan


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class SuccessfulSearchClient:
    """Fake MCP client used to verify prompt-time search."""

    def search_web(self, query: str, *, max_results: int = 5) -> SearchResponse:
        del max_results
        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    title="FastAPI release notes",
                    url="https://fastapi.tiangolo.com/release-notes/",
                    snippet="Release notes",
                )
            ],
        )


class FailingSearchClient:
    """Fake MCP client used to verify graceful degradation."""

    def search_web(self, query: str, *, max_results: int = 5) -> SearchResponse:
        del query, max_results
        raise RuntimeError("server unavailable")


class FakePlanningAgent:
    """Fake planning agent used to isolate runtime wiring."""

    def build_plan(self, prompt: str, **_: object) -> AgentPlan:
        return AgentPlan(
            summary=f"Plan for: {prompt}",
            planned_files=["src/devmate/agent_runtime.py", "tests/test_agent_runtime.py"],
            implementation_steps=[
                "Collect the prompt context.",
                "Produce the next code changes.",
                "Verify the behavior with tests.",
            ],
            used_model=False,
        )


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def _write_config(path: Path, *, docs_dir: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[app]",
                'project_name = "DevMate"',
                f'docs_dir = "{docs_dir.as_posix()}"',
                'log_level = "INFO"',
                "",
                "[model]",
                'ai_base_url = "https://api.minimax.io/v1"',
                'api_key = "test"',
                'model_name = "MiniMax-M2"',
                'embedding_model_name = ""',
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
                "top_k = 4",
                "",
                "[langsmith]",
                "langchain_tracing_v2 = true",
                'langchain_api_key = "test"',
                "",
                "[skills]",
                'skills_dir = ".skills"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_prompt_triggers_web_search() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        docs_dir = root / "docs"
        docs_dir.mkdir()
        (docs_dir / "guide.md").write_text(
            "FastAPI project guidelines and release process.",
            encoding="utf-8",
        )
        _write_config(config_path, docs_dir=docs_dir)

        settings = load_settings(config_path)
        runtime = DevMateRuntime(
            settings,
            search_client=SuccessfulSearchClient(),
            planning_agent=FakePlanningAgent(),
        )

        result = runtime.handle_prompt("latest FastAPI release notes")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.web_search_attempted is True
    assert result.summary == "Plan for: latest FastAPI release notes"
    assert len(result.web_results) == 1
    assert result.web_results[0].title == "FastAPI release notes"
    assert result.planned_files == [
        "src/devmate/agent_runtime.py",
        "tests/test_agent_runtime.py",
    ]
    assert result.implementation_steps[0] == "Collect the prompt context."
    assert result.agent_used_model is False


def test_prompt_gracefully_handles_web_search_failure() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        docs_dir = root / "docs"
        docs_dir.mkdir()
        (docs_dir / "guide.md").write_text(
            "FastAPI project guidelines.",
            encoding="utf-8",
        )
        _write_config(config_path, docs_dir=docs_dir)

        settings = load_settings(config_path)
        runtime = DevMateRuntime(
            settings,
            search_client=FailingSearchClient(),
            planning_agent=FakePlanningAgent(),
        )

        result = runtime.handle_prompt("latest FastAPI release notes")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.web_search_attempted is True
    assert result.web_results == []
    assert result.web_search_error == "server unavailable"
    assert result.summary == "Plan for: latest FastAPI release notes"
