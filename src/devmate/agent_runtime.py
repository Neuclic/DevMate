"""Minimal agent runtime used by the project skeleton."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from devmate.config_loader import AppSettings
from devmate.mcp_client import SearchMcpClient, SearchResult
from devmate.planning_agent import PlanningAgent
from devmate.rag_pipeline import KnowledgeBasePipeline

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptResult:
    """Structured response returned by the runtime."""

    summary: str
    planned_files: list[str]
    implementation_steps: list[str]
    retrieved_sources: list[str]
    web_results: list[SearchResult]
    web_search_attempted: bool
    agent_used_model: bool
    web_search_error: str | None = None
    agent_error: str | None = None


class DevMateRuntime:
    """A minimal runtime that can outline the next project step."""

    def __init__(
        self,
        settings: AppSettings,
        search_client: SearchMcpClient | None = None,
        planning_agent: PlanningAgent | None = None,
    ) -> None:
        self.settings = settings
        self.knowledge_base = KnowledgeBasePipeline(Path(settings.app.docs_dir))
        self.search_client = search_client or SearchMcpClient(
            server_url=settings.mcp.server_url,
            transport=settings.mcp.transport,
            tool_timeout_seconds=settings.mcp.tool_timeout_seconds,
            healthcheck_timeout_seconds=settings.mcp.healthcheck_timeout_seconds,
        )
        self.planning_agent = planning_agent or PlanningAgent(settings)

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

        plan = self.planning_agent.build_plan(
            prompt,
            local_snippets=snippets,
            web_results=web_results,
        )

        return PromptResult(
            summary=plan.summary,
            planned_files=plan.planned_files,
            implementation_steps=plan.implementation_steps,
            retrieved_sources=sources,
            web_results=web_results,
            web_search_attempted=web_search_attempted,
            agent_used_model=plan.used_model,
            web_search_error=web_search_error,
            agent_error=plan.model_error,
        )
