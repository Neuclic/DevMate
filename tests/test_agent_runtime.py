"""Tests for prompt-time MCP search integration."""

from __future__ import annotations

from pathlib import Path

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import load_settings
from devmate.mcp_client import SearchResponse, SearchResult


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


def _write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[app]",
                'project_name = "DevMate"',
                'docs_dir = "docs"',
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


def test_prompt_triggers_web_search(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text(
        "FastAPI project guidelines and release process.",
        encoding="utf-8",
    )
    _write_config(config_path)

    settings = load_settings(config_path)
    runtime = DevMateRuntime(settings, search_client=SuccessfulSearchClient())

    result = runtime.handle_prompt("latest FastAPI release notes")

    assert result.web_search_attempted is True
    assert len(result.web_results) == 1
    assert result.web_results[0].title == "FastAPI release notes"


def test_prompt_gracefully_handles_web_search_failure(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("FastAPI project guidelines.", encoding="utf-8")
    _write_config(config_path)

    settings = load_settings(config_path)
    runtime = DevMateRuntime(settings, search_client=FailingSearchClient())

    result = runtime.handle_prompt("latest FastAPI release notes")

    assert result.web_search_attempted is True
    assert result.web_results == []
    assert result.web_search_error == "server unavailable"
