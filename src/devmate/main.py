"""CLI entry point for the DevMate skeleton."""

from __future__ import annotations

import argparse
from datetime import datetime
import logging
from pathlib import Path

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import AppSettings
from devmate.config_loader import load_settings
from devmate.logging_config import configure_logging
from devmate.mcp_client import SearchMcpClient
from devmate.mcp_server import run_mcp_server
from devmate.observability import configure_langsmith
from devmate.observability import is_placeholder
from devmate.observability import langsmith_is_configured
from devmate.observability import latest_trace_info
from devmate.observability import trace_start_time
from devmate.rag_pipeline import KnowledgeBasePipeline
from devmate.session_store import SessionStore
from devmate.skill_registry import SkillRegistry
from devmate.web_app import run_web_app

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="DevMate project skeleton")
    parser.add_argument(
        "--config",
        default="config.toml",
        help="Path to the TOML configuration file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Application log level.",
    )
    parser.add_argument(
        "--config-check",
        action="store_true",
        help="Validate which providers are effectively configured after local overrides.",
    )
    parser.add_argument(
        "--print-trace-url",
        action="store_true",
        help="Print the latest LangSmith trace URL after a prompt run.",
    )
    parser.add_argument(
        "--session-id",
        default="",
        help="Optional persisted session id used to carry multi-turn context.",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List saved local sessions only.",
    )
    parser.add_argument(
        "--share-trace",
        action="store_true",
        help="Create and print a shareable LangSmith trace URL after a prompt run.",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="Optional prompt used to simulate one agent run.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate files from the resulting implementation plan.",
    )
    parser.add_argument(
        "--output-dir",
        default="generated-output",
        help="Target directory used when --generate is enabled.",
    )
    parser.add_argument(
        "--save-skill",
        default="",
        help="Save the generated plan as a reusable skill note with this name.",
    )
    parser.add_argument(
        "--list-skills",
        action="store_true",
        help="List saved skills only.",
    )
    parser.add_argument(
        "--skill-query",
        default="",
        help="Search saved skills only.",
    )
    parser.add_argument(
        "--skill-limit",
        type=int,
        default=3,
        help="Maximum number of saved skills to return.",
    )
    parser.add_argument(
        "--serve-mcp",
        action="store_true",
        help="Run the local MCP server using the configured Streamable HTTP endpoint.",
    )
    parser.add_argument(
        "--serve-web",
        action="store_true",
        help="Run the local DevMate web UI.",
    )
    parser.add_argument(
        "--web-host",
        default="127.0.0.1",
        help="Host used when serving the local web UI.",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8765,
        help="Port used when serving the local web UI.",
    )
    parser.add_argument(
        "--mcp-query",
        default="",
        help="Send one query to the configured MCP server through the client.",
    )
    parser.add_argument(
        "--rag-query",
        default="",
        help="Search the local RAG knowledge base only.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of Tavily results to request through MCP.",
    )
    parser.add_argument(
        "--rag-limit",
        type=int,
        default=3,
        help="Maximum number of local RAG matches to return.",
    )
    return parser


def resolve_rag_manifest_path(settings: AppSettings) -> Path:
    """Resolve the manifest path used by the local Chroma index."""
    docs_dir = Path(settings.app.docs_dir)
    persist_directory = Path(settings.rag.persist_directory)
    if persist_directory.is_absolute():
        return persist_directory / "manifest.json"
    return docs_dir.parent / persist_directory / "manifest.json"


def resolve_skills_dir(settings: AppSettings) -> Path:
    """Resolve the configured skills directory."""
    skills_dir = Path(settings.skills.skills_dir)
    if skills_dir.is_absolute():
        return skills_dir
    return Path.cwd() / skills_dir


def resolve_sessions_dir() -> Path:
    """Resolve the local session persistence directory."""
    return Path.cwd() / ".sessions"


def main() -> int:
    """Run the CLI application."""
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)
    settings = load_settings(Path(args.config))
    configure_langsmith(settings)

    if args.config_check:
        LOGGER.info(
            "MiniMax model configured: %s",
            not is_placeholder(settings.model.api_key),
        )
        LOGGER.info("MiniMax model name: %s", settings.model.model_name)
        LOGGER.info("MiniMax base URL: %s", settings.model.ai_base_url)
        LOGGER.info(
            "Embedding configured: %s",
            not is_placeholder(settings.model.embedding_api_key),
        )
        LOGGER.info("Embedding model name: %s", settings.model.embedding_model_name)
        LOGGER.info(
            "Tavily configured: %s",
            not is_placeholder(settings.search.tavily_api_key),
        )
        LOGGER.info("MCP server URL: %s", settings.mcp.server_url)
        LOGGER.info("Skills directory: %s", resolve_skills_dir(settings))
        LOGGER.info(
            "LangSmith configured: %s",
            langsmith_is_configured(settings),
        )
        LOGGER.info("LangSmith project: %s", settings.langsmith.project_name)
        LOGGER.info("LangSmith endpoint: %s", settings.langsmith.endpoint)
        return 0

    if args.serve_mcp:
        run_mcp_server(settings)
        return 0

    if args.serve_web:
        LOGGER.info(
            "Starting DevMate web UI at http://%s:%d",
            args.web_host,
            args.web_port,
        )
        run_web_app(settings, host=args.web_host, port=args.web_port)
        return 0

    if args.mcp_query:
        client = SearchMcpClient(
            server_url=settings.mcp.server_url,
            transport=settings.mcp.transport,
            tool_timeout_seconds=settings.mcp.tool_timeout_seconds,
            healthcheck_timeout_seconds=settings.mcp.healthcheck_timeout_seconds,
        )
        response = client.search_web(
            args.mcp_query,
            max_results=args.max_results,
        )
        LOGGER.info("MCP query: %s", response.query)
        LOGGER.info("MCP results: %d", len(response.results))
        for item in response.results:
            LOGGER.info("%s | %s", item.title, item.url)
        return 0

    if args.rag_query:
        pipeline = KnowledgeBasePipeline(
            docs_dir=Path(settings.app.docs_dir),
            rag_settings=settings.rag,
            model_settings=settings.model,
        )
        results = pipeline.search(args.rag_query, limit=args.rag_limit)
        manifest_path = resolve_rag_manifest_path(settings)
        LOGGER.info("RAG query: %s", args.rag_query)
        LOGGER.info("RAG results: %d", len(results))
        LOGGER.info("RAG manifest: %s", manifest_path)
        LOGGER.info("RAG index ready: %s", manifest_path.exists())
        for item in results:
            LOGGER.info("%s | %.4f | %s", item.source_name, item.score, item.excerpt)
        return 0

    skills_registry = SkillRegistry(resolve_skills_dir(settings))

    if args.list_skills:
        skills = skills_registry.list_skills()
        LOGGER.info("Saved skills: %d", len(skills))
        for skill in skills:
            LOGGER.info("%s | %s", skill.name, skill.summary)
        return 0

    if args.skill_query:
        skills = skills_registry.search(args.skill_query, limit=args.skill_limit)
        LOGGER.info("Skill query: %s", args.skill_query)
        LOGGER.info("Skill results: %d", len(skills))
        for skill in skills:
            LOGGER.info("%s | %s", skill.name, ", ".join(skill.keywords) or "no-keywords")
        return 0

    session_store = SessionStore(resolve_sessions_dir())

    if args.list_sessions:
        sessions = session_store.list_sessions()
        LOGGER.info("Saved sessions: %d", len(sessions))
        for session in sessions:
            LOGGER.info(
                "%s | %s | turns=%d | updated=%s",
                session.session_id,
                session.title,
                session.turn_count,
                session.updated_at,
            )
        return 0

    runtime = DevMateRuntime(
        settings=settings,
        skill_registry=skills_registry,
        session_store=session_store,
    )

    if args.prompt:
        started_at = trace_start_time()
        result = runtime.handle_prompt(
            args.prompt,
            save_skill_name=args.save_skill or None,
            generate_output_dir=Path(args.output_dir) if args.generate else None,
            session_id=args.session_id or None,
        )
        if result.session_id:
            LOGGER.info("Session id: %s", result.session_id)
        LOGGER.info("Prompt summary: %s", result.summary)
        LOGGER.info(
            "Planning mode: %s",
            "llm" if result.agent_used_model else "fallback",
        )
        LOGGER.info("Planned files: %s", ", ".join(result.planned_files))
        LOGGER.info(
            "Implementation steps: %s",
            " | ".join(result.implementation_steps),
        )
        if result.retrieved_sources:
            LOGGER.info(
                "Local knowledge sources: %s",
                ", ".join(result.retrieved_sources),
            )
        if result.matched_skills:
            LOGGER.info("Matched skills: %s", ", ".join(result.matched_skills))
        if result.web_results:
            LOGGER.info("Web search results: %d", len(result.web_results))
            for item in result.web_results:
                LOGGER.info("%s | %s", item.title, item.url)
        elif result.web_search_error:
            LOGGER.warning("Web search error: %s", result.web_search_error)
        if result.saved_skill_path:
            LOGGER.info("Saved skill: %s", result.saved_skill_path)
        if result.agent_error:
            LOGGER.warning("Planning agent error: %s", result.agent_error)
        if result.generation_output_dir:
            LOGGER.info("Generated output dir: %s", result.generation_output_dir)
            LOGGER.info(
                "Generation mode: %s",
                "llm" if result.generation_used_model else "template-fallback",
            )
            if result.generated_files:
                LOGGER.info("Generated files: %s", ", ".join(result.generated_files))
            if result.generated_created_files:
                LOGGER.info("Created files: %s", ", ".join(result.generated_created_files))
            if result.generated_modified_files:
                LOGGER.info("Modified files: %s", ", ".join(result.generated_modified_files))
        if result.generation_error:
            LOGGER.warning("Generation model error: %s", result.generation_error)
        if args.print_trace_url or args.share_trace:
            trace = latest_trace_info(
                settings,
                started_at=started_at,
                share_public=args.share_trace or settings.langsmith.share_public_traces,
            )
            if trace is not None:
                LOGGER.info("LangSmith trace URL: %s", trace.run_url)
                if trace.shared_url:
                    LOGGER.info("LangSmith shared trace URL: %s", trace.shared_url)
        return 0

    LOGGER.info("DevMate skeleton is ready.")
    LOGGER.info("Project name: %s", settings.app.project_name)
    LOGGER.info("Provide --prompt to simulate one planning run.")
    return 0
