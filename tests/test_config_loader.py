"""Basic tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

from devmate.config_loader import load_settings


def test_load_settings_reads_required_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[app]",
                'project_name = "DevMate"',
                'docs_dir = "docs"',
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
                "",
                "[mcp]",
                'server_url = "http://localhost:8001/mcp"',
                'transport = "streamable_http"',
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

    assert settings.app.project_name == "DevMate"
    assert settings.mcp.transport == "streamable_http"
    assert settings.rag.top_k == 4
