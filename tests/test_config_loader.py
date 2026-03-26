"""Basic tests for configuration loading."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from devmate.config_loader import load_settings


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


def test_load_settings_reads_required_sections() -> None:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    try:
        config_path = root / "config.toml"
        docs_dir = root / "docs"
        docs_dir.mkdir()
        config_path.write_text(
            "\n".join(
                [
                    "[app]",
                    'project_name = "DevMate"',
                    f'docs_dir = "{docs_dir.as_posix()}"',
                    'log_level = "INFO"',
                    "",
                    "[model]",
                    'ai_base_url = "https://api.openai.com/v1"',
                    'api_key = "test"',
                    'model_name = "gpt-4o"',
                    'embedding_model_name = "text-embedding-3-small"',
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

        settings = load_settings(config_path)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert settings.app.project_name == "DevMate"
    assert settings.search.default_max_results == 5
    assert settings.mcp.transport == "streamable_http"
    assert settings.mcp.tool_timeout_seconds == 30.0
    assert settings.rag.top_k == 4
