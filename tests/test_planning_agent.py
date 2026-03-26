"""Unit tests for the planning agent."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from devmate.config_loader import load_settings
from devmate.mcp_client import SearchResult
from devmate.planning_agent import PlanningAgent
from devmate.rag_pipeline import KnowledgeSnippet


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class FakeMessage:
    """Minimal message wrapper used by the fake model."""

    def __init__(self, content: object) -> None:
        self.content = content


class FakeModel:
    """Fake model that returns a fixed response."""

    def __init__(self, content: object) -> None:
        self.content = content

    def invoke(self, messages: object) -> FakeMessage:
        del messages
        return FakeMessage(self.content)


class FailingModel:
    """Fake model that raises during invocation."""

    def invoke(self, messages: object) -> FakeMessage:
        del messages
        raise RuntimeError("model unavailable")


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def _write_config(path: Path, *, docs_dir: Path, api_key: str) -> None:
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
                f'api_key = "{api_key}"',
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


def test_planning_agent_parses_json_response() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        docs_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, api_key="test")
        settings = load_settings(config_path)
        model = FakeModel(
            """```json
{
  \"summary\": \"Build the runtime integration next.\",
  \"planned_files\": [\"src/devmate/agent_runtime.py\", \"tests/test_agent_runtime.py\"],
  \"implementation_steps\": [
    \"Connect the runtime to the planning agent.\",
    \"Expose the plan through the CLI output.\",
    \"Verify the behavior with unit tests.\"
  ]
}
```"""
        )
        agent = PlanningAgent(settings, model=model)

        plan = agent.build_plan(
            "connect the agent",
            local_snippets=[
                KnowledgeSnippet(
                    source_name="architecture.md",
                    excerpt="Runtime architecture details.",
                    score=2,
                )
            ],
            web_results=[
                SearchResult(
                    title="LangChain docs",
                    url="https://python.langchain.com/",
                    snippet="Planner patterns.",
                )
            ],
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert plan.used_model is True
    assert plan.summary == "Build the runtime integration next."
    assert plan.planned_files == [
        "src/devmate/agent_runtime.py",
        "tests/test_agent_runtime.py",
    ]
    assert plan.implementation_steps[1] == "Expose the plan through the CLI output."


def test_planning_agent_falls_back_without_real_model_config() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        docs_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(
            config_path,
            docs_dir=docs_dir,
            api_key="your_minimax_api_key_here",
        )
        settings = load_settings(config_path)
        agent = PlanningAgent(settings)

        plan = agent.build_plan(
            "build a website",
            local_snippets=[
                KnowledgeSnippet(
                    source_name="internal_frontend_guidelines.md",
                    excerpt="Use clear sections and bold typography.",
                    score=1,
                )
            ],
            web_results=[],
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert plan.used_model is False
    assert plan.model_error is None
    assert (
        plan.summary
        == "Prepared an initial implementation plan from 1 local snippets and 0 web results."
    )
    assert "docs/internal_frontend_guidelines.md" in plan.planned_files


def test_planning_agent_falls_back_on_model_error() -> None:
    root = _make_test_root()
    try:
        docs_dir = root / "docs"
        docs_dir.mkdir()
        config_path = root / "config.toml"
        _write_config(config_path, docs_dir=docs_dir, api_key="test")
        settings = load_settings(config_path)
        agent = PlanningAgent(settings, model=FailingModel())

        plan = agent.build_plan(
            "build an api service",
            local_snippets=[],
            web_results=[],
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert plan.used_model is False
    assert plan.model_error == "model unavailable"
    assert "docs/architecture.md" in plan.planned_files
