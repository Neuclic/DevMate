"""Tests for CLI argument parsing helpers."""

from __future__ import annotations

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
from devmate.main import build_parser, resolve_rag_manifest_path


def _settings() -> AppSettings:
    return AppSettings(
        app=AppSection(
            project_name="DevMate",
            docs_dir="docs",
            log_level="INFO",
        ),
        model=ModelSection(
            ai_base_url="https://api.minimax.io/v1",
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
            langchain_api_key="test",
        ),
        skills=SkillsSection(
            skills_dir=".skills",
        ),
    )


def test_build_parser_parses_rag_query_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(["--rag-query", "frontend layout", "--rag-limit", "2"])

    assert args.rag_query == "frontend layout"
    assert args.rag_limit == 2


def test_resolve_rag_manifest_path_uses_docs_parent_for_relative_paths() -> None:
    manifest_path = resolve_rag_manifest_path(_settings())

    assert manifest_path.name == "manifest.json"
    assert manifest_path.parent.name == "devmate-docs"
    assert manifest_path.parent.parent.name == ".chroma"
