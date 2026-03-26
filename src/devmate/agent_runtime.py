"""Minimal agent runtime used by the project skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devmate.config_loader import AppSettings
from devmate.rag_pipeline import KnowledgeBasePipeline


@dataclass(frozen=True)
class PromptResult:
    """Structured response returned by the runtime."""

    summary: str
    planned_files: list[str]
    retrieved_sources: list[str]


class DevMateRuntime:
    """A minimal runtime that can outline the next project step."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.knowledge_base = KnowledgeBasePipeline(Path(settings.app.docs_dir))

    def handle_prompt(self, prompt: str) -> PromptResult:
        """Simulate a planning run for one prompt."""
        snippets = self.knowledge_base.search(prompt, limit=self.settings.rag.top_k)
        sources = [snippet.source_name for snippet in snippets]
        planned_files = [
            "pyproject.toml",
            "config.toml",
            "src/devmate/main.py",
            "Dockerfile",
            "docker-compose.yml",
        ]
        summary = (
            "Skeleton planning run completed. "
            "Next implementation step is to replace placeholder MCP, RAG, "
            "and Skills modules with real integrations."
        )
        return PromptResult(
            summary=summary,
            planned_files=planned_files,
            retrieved_sources=sources,
        )
