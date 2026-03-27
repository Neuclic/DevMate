"""Tests for project file generation."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from devmate.config_loader import load_settings
from devmate.planning_agent import AgentPlan
from devmate.project_generator import ProjectGenerator


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class FakeMessage:
    """Minimal message wrapper used by the fake model."""

    def __init__(self, content: object) -> None:
        self.content = content


class FakeModel:
    """Fake model that returns a fixed JSON payload."""

    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, messages: object) -> FakeMessage:
        del messages
        return FakeMessage(self.content)


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


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
                'persist_directory = ".chroma/test-generator"',
                "chunk_size = 400",
                "chunk_overlap = 40",
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


def _plan() -> AgentPlan:
    return AgentPlan(
        summary="Build a map website.",
        planned_files=["index.html", "css/styles.css", "README.md"],
        implementation_steps=[
            "Create the page shell.",
            "Add responsive styles.",
            "Document how to run the site.",
        ],
        used_model=True,
    )


def test_project_generator_uses_template_fallback_when_model_is_not_configured() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        object.__setattr__(settings.model, 'api_key', 'your_minimax_api_key_here')
        generator = ProjectGenerator(settings)

        result = generator.generate_project(
            "build a responsive map website",
            _plan(),
            output_dir=root / "out",
        )

        index_content = (root / "out" / "index.html").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.used_model is False
    assert len(result.files) == 3
    assert "Trail Atlas" in index_content


def test_project_generator_writes_model_generated_files() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        model = FakeModel(
            """{
  \"files\": [
    {\"path\": \"index.html\", \"content\": \"<h1>Hello</h1>\"},
    {\"path\": \"README.md\", \"content\": \"# Demo\"}
  ]
}"""
        )
        generator = ProjectGenerator(settings, model=model)

        result = generator.generate_project(
            "build a responsive map website",
            _plan(),
            output_dir=root / "out",
        )

        index_content = (root / "out" / "index.html").read_text(encoding="utf-8")
        css_content = (root / "out" / "css" / "styles.css").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.used_model is True
    assert "<h1>Hello</h1>" in index_content
    assert "background" in css_content


def test_project_generator_marks_existing_files_as_modified() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        object.__setattr__(settings.model, 'api_key', 'your_minimax_api_key_here')
        generator = ProjectGenerator(settings)
        output_dir = root / "out"
        output_dir.mkdir()
        (output_dir / "README.md").write_text("# Existing\n", encoding="utf-8")

        result = generator.generate_project(
            "update the generated project readme",
            _plan(),
            output_dir=output_dir,
        )

        readme_content = (output_dir / "README.md").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    modified = [item.path for item in result.files if item.existed_before]
    assert modified == ["README.md"]
    assert "DevMate Update" in readme_content