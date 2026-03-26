"""Minimal agent runtime used by the project skeleton."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from devmate.config_loader import AppSettings
from devmate.mcp_client import SearchMcpClient, SearchResult
from devmate.rag_pipeline import KnowledgeBasePipeline

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptResult:
    """Structured response returned by the runtime."""

    summary: str
    planned_files: list[str]
    retrieved_sources: list[str]
    web_results: list[SearchResult]
    web_search_attempted: bool
    web_search_error: str | None = None


class DevMateRuntime:
    """A minimal runtime that can outline the next project step."""

    def __init__(
        self,
        settings: AppSettings,
        search_client: SearchMcpClient | None = None,
    ) -> None:
        self.settings = settings
        self.knowledge_base = KnowledgeBasePipeline(Path(settings.app.docs_dir))
        self.search_client = search_client or SearchMcpClient(
            server_url=settings.mcp.server_url,
            transport=settings.mcp.transport,
            tool_timeout_seconds=settings.mcp.tool_timeout_seconds,
            healthcheck_timeout_seconds=settings.mcp.healthcheck_timeout_seconds,
        )

    def handle_prompt(self, prompt: str) -> PromptResult:
        """Simulate a planning run for one prompt."""
        snippets = self.knowledge_base.search(prompt, limit=self.settings.rag.top_k)
        sources = [snippet.source_name for snippet in snippets]
        web_results: list[SearchResult] = []
        web_search_error: str | None = None
        web_search_attempted = False

        if prompt.strip():
            web_search_attempted = True
            try:
                response = self.search_client.search_web(
                    prompt,
                    max_results=self.settings.search.default_max_results,
                )
                web_results = response.results
            except Exception as exc:
                web_search_error = str(exc)
                LOGGER.warning("Web search failed for prompt '%s': %s", prompt, exc)

        planned_files = [
            "pyproject.toml",
            "config.toml",
            "src/devmate/main.py",
            "Dockerfile",
            "docker-compose.yml",
        ]
        summary_parts = [
            "Skeleton planning run completed.",
            f"Local RAG matches: {len(sources)}.",
        ]
        if web_search_attempted and web_results:
            summary_parts.append(f"MCP web results: {len(web_results)}.")
        elif web_search_attempted and web_search_error:
            summary_parts.append(f"MCP web search unavailable: {web_search_error}")

        return PromptResult(
            summary=" ".join(summary_parts),
            planned_files=planned_files,
            retrieved_sources=sources,
            web_results=web_results,
            web_search_attempted=web_search_attempted,
            web_search_error=web_search_error,
        )
