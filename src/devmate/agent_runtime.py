"""Minimal agent runtime used by the project skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from langsmith.run_helpers import traceable

from devmate.config_loader import AppSettings
from devmate.mcp_client import SearchMcpClient, SearchResult
from devmate.planning_agent import PlanningAgent
from devmate.project_generator import GenerationResult, ProjectGenerator
from devmate.rag_pipeline import KnowledgeBasePipeline
from devmate.skill_registry import SkillNote, SkillRegistry


@dataclass(frozen=True)
class PromptResult:
    """Structured response returned by the runtime."""

    summary: str
    planned_files: list[str]
    implementation_steps: list[str]
    retrieved_sources: list[str]
    matched_skills: list[str]
    web_results: list[SearchResult]
    web_search_attempted: bool
    agent_used_model: bool
    generation_output_dir: str | None = None
    generated_files: list[str] | None = None
    generated_created_files: list[str] | None = None
    generated_modified_files: list[str] | None = None
    generation_used_model: bool = False
    saved_skill_path: str | None = None
    web_search_error: str | None = None
    agent_error: str | None = None
    generation_error: str | None = None


class DevMateRuntime:
    """A minimal runtime that can outline the next project step."""

    def __init__(
        self,
        settings: AppSettings,
        search_client: SearchMcpClient | None = None,
        planning_agent: PlanningAgent | None = None,
        skill_registry: SkillRegistry | None = None,
        project_generator: ProjectGenerator | None = None,
    ) -> None:
        self.settings = settings
        self.knowledge_base = KnowledgeBasePipeline(
            docs_dir=Path(settings.app.docs_dir),
            rag_settings=settings.rag,
            model_settings=settings.model,
        )
        self.search_client = search_client or SearchMcpClient(
            server_url=settings.mcp.server_url,
            transport=settings.mcp.transport,
            tool_timeout_seconds=settings.mcp.tool_timeout_seconds,
            healthcheck_timeout_seconds=settings.mcp.healthcheck_timeout_seconds,
        )
        self.skill_registry = skill_registry or SkillRegistry(Path(settings.skills.skills_dir))
        self.planning_agent = planning_agent or PlanningAgent(settings)
        self.project_generator = project_generator or ProjectGenerator(settings)

    @traceable(run_type="chain", name="devmate_handle_prompt")
    def handle_prompt(
        self,
        prompt: str,
        *,
        save_skill_name: str | None = None,
        generate_output_dir: Path | None = None,
    ) -> PromptResult:
        """Simulate a planning run for one prompt."""
        plan = self.planning_agent.build_plan(
            prompt,
            knowledge_base=self.knowledge_base,
            search_client=self.search_client,
            skill_registry=self.skill_registry,
        )
        sources = [snippet.source_name for snippet in plan.local_snippets]
        matched_skills = [note.name for note in plan.matched_skills]
        saved_skill_path: str | None = None
        generation: GenerationResult | None = None

        if save_skill_name:
            note = self._build_skill_note(save_skill_name, prompt, plan)
            saved_skill_path = str(self.skill_registry.save(note))

        if generate_output_dir is not None:
            generation = self.project_generator.generate_project(
                prompt,
                plan,
                output_dir=generate_output_dir,
            )

        return PromptResult(
            summary=plan.summary,
            planned_files=plan.planned_files,
            implementation_steps=plan.implementation_steps,
            retrieved_sources=sources,
            matched_skills=matched_skills,
            web_results=plan.web_results,
            web_search_attempted=plan.web_search_attempted,
            agent_used_model=plan.used_model,
            generation_output_dir=generation.output_dir if generation is not None else None,
            generated_files=[item.path for item in generation.files] if generation is not None else None,
            generated_created_files=(
                [item.path for item in generation.files if not item.existed_before]
                if generation is not None
                else None
            ),
            generated_modified_files=(
                [item.path for item in generation.files if item.existed_before]
                if generation is not None
                else None
            ),
            generation_used_model=generation.used_model if generation is not None else False,
            saved_skill_path=saved_skill_path,
            web_search_error=plan.web_search_error,
            agent_error=plan.model_error,
            generation_error=generation.model_error if generation is not None else None,
        )

    @staticmethod
    def _build_skill_note(name: str, prompt: str, plan: object) -> SkillNote:
        keywords = [
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9_]+", f"{name} {prompt}")
            if len(token) >= 4
        ]
        deduped_keywords: list[str] = []
        for token in keywords:
            if token not in deduped_keywords:
                deduped_keywords.append(token)
        return SkillNote(
            name=name,
            summary=str(plan.summary),
            steps=list(plan.implementation_steps),
            keywords=deduped_keywords[:8],
        )
