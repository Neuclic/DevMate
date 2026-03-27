"""Tests for LangSmith observability helpers."""

from __future__ import annotations

import os

from devmate.config_loader import (
    AppSection,
    AppSettings,
    LangSmithSection,
    McpSection,
    ModelSection,
    RagSection,
    SearchSection,
    SkillsSection,
)
from devmate.observability import configure_langsmith, langsmith_is_configured


def _settings(api_key: str) -> AppSettings:
    return AppSettings(
        app=AppSection(project_name="DevMate", docs_dir="docs", log_level="INFO"),
        model=ModelSection(
            ai_base_url="https://api.minimaxi.com/v1",
            api_key="test",
            model_name="MiniMax-M2",
            embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            embedding_api_key="test",
            embedding_model_name="text-embedding-v4",
        ),
        search=SearchSection(
            tavily_api_key="test",
            default_max_results=5,
            request_timeout_seconds=20.0,
        ),
        mcp=McpSection(
            server_url="http://localhost:8001/mcp",
            transport="streamable_http",
            tool_timeout_seconds=30.0,
            healthcheck_timeout_seconds=5.0,
        ),
        rag=RagSection(
            provider="chromadb",
            collection_name="devmate-docs",
            persist_directory=".chroma/devmate-docs",
            chunk_size=800,
            chunk_overlap=120,
            top_k=4,
        ),
        langsmith=LangSmithSection(
            langchain_tracing_v2=True,
            langchain_api_key=api_key,
            project_name="DevMate Tests",
            endpoint="https://api.smith.langchain.com",
            share_public_traces=False,
        ),
        skills=SkillsSection(skills_dir=".skills"),
    )


def test_langsmith_is_configured_rejects_placeholder() -> None:
    assert langsmith_is_configured(_settings("your_langchain_api_key_here")) is False
    assert langsmith_is_configured(_settings("lsv2_pt_test")) is True


def test_configure_langsmith_sets_environment_variables() -> None:
    settings = _settings("lsv2_pt_test")

    configured = configure_langsmith(settings)

    assert configured is True
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "DevMate Tests"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://api.smith.langchain.com"