"""Minimal agent runtime used by the project skeleton."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import re
import time

from langsmith.run_helpers import traceable

from devmate.config_loader import AppSettings
from devmate.mcp_client import SearchMcpClient, SearchResult
from devmate.planning_agent import AgentPlan, PlanningAgent
from devmate.project_generator import GenerationResult, ProjectGenerator, GeneratedFile
from devmate.rag_pipeline import KnowledgeBasePipeline, KnowledgeSnippet
from devmate.search_policy import should_search_web
from devmate.session_store import SessionStore, SessionTurn
from devmate.skill_registry import SkillNote, SkillRegistry


@dataclass(frozen=True)
class PromptResult:
    """Structured response returned by the runtime."""

    session_id: str | None
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
    """A minimal runtime that can outline and generate the next project step."""

    def __init__(
        self,
        settings: AppSettings,
        search_client: SearchMcpClient | None = None,
        planning_agent: PlanningAgent | None = None,
        skill_registry: SkillRegistry | None = None,
        project_generator: ProjectGenerator | None = None,
        session_store: SessionStore | None = None,
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
        self.session_store = session_store or SessionStore(Path(".sessions"))

    @traceable(run_type="chain", name="devmate_handle_prompt")
    def handle_prompt(
        self,
        prompt: str,
        *,
        save_skill_name: str | None = None,
        generate_output_dir: Path | None = None,
        session_id: str | None = None,
    ) -> PromptResult:
        """Run one prompt synchronously."""
        plan, web_search_attempted, web_search_error = self._build_plan(prompt, session_id)
        generation: GenerationResult | None = None
        saved_skill_path: str | None = None

        if save_skill_name:
            note = self._build_skill_note(save_skill_name, prompt, plan)
            saved_skill_path = str(self.skill_registry.save(note))

        if generate_output_dir is not None:
            generation = self.project_generator.generate_project(
                prompt,
                plan,
                output_dir=generate_output_dir,
            )

        result = self._build_prompt_result(
            session_id=session_id,
            plan=plan,
            generation=generation,
            saved_skill_path=saved_skill_path,
            web_search_attempted=web_search_attempted,
            web_search_error=web_search_error,
        )
        self._persist_turn(session_id, prompt, result)
        return result

    def stream_prompt(
        self,
        prompt: str,
        *,
        save_skill_name: str | None = None,
        generate_output_dir: Path | None = None,
        session_id: str,
    ) -> Iterator[dict[str, object]]:
        """Run one prompt and yield SSE-friendly events as progress becomes available."""
        search_payload: list[dict[str, object]] = []
        web_search_attempted = False
        web_search_error: str | None = None
        generation: GenerationResult | None = None
        saved_skill_path: str | None = None

        def emit_step(
            step_id: str,
            title: str,
            description: str,
            status: str,
            *,
            started_at: float | None = None,
            output: str | None = None,
        ) -> dict[str, object]:
            payload: dict[str, object] = {
                "type": "planning",
                "step": {
                    "id": step_id,
                    "title": title,
                    "description": description,
                    "status": status,
                },
            }
            if started_at is not None:
                payload["step"]["duration_ms"] = int((time.perf_counter() - started_at) * 1000)
            if output:
                payload["step"]["output"] = output
            return payload

        def append_search_results(items: list[dict[str, object]]) -> dict[str, object]:
            search_payload.extend(items)
            return {"type": "search", "results": list(search_payload)}

        try:
            history = self._conversation_history(session_id)

            local_started = time.perf_counter()
            yield emit_step(
                "local-search",
                "Search local knowledge",
                "Reading project docs and local implementation notes.",
                "running",
            )
            local_snippets = self.knowledge_base.search(prompt, limit=self.settings.rag.top_k)
            local_results = [self._local_search_result(snippet) for snippet in local_snippets]
            if local_results:
                yield append_search_results(local_results)
            yield emit_step(
                "local-search",
                "Search local knowledge",
                "Reading project docs and local implementation notes.",
                "completed",
                started_at=local_started,
                output=f"{len(local_snippets)} local matches",
            )

            skills_started = time.perf_counter()
            yield emit_step(
                "skill-search",
                "Search saved skills",
                "Looking for reusable task patterns from the skill library.",
                "running",
            )
            matched_skills = self.skill_registry.search(prompt, limit=3)
            skill_results = [self._skill_search_result(note) for note in matched_skills]
            if skill_results:
                yield append_search_results(skill_results)
            yield emit_step(
                "skill-search",
                "Search saved skills",
                "Looking for reusable task patterns from the skill library.",
                "completed",
                started_at=skills_started,
                output=f"{len(matched_skills)} skill matches",
            )

            web_results: list[SearchResult] = []
            if self._should_search_web(prompt):
                web_search_attempted = True
                web_started = time.perf_counter()
                yield emit_step(
                    "web-search",
                    "Search the web",
                    "Checking external sources for the latest APIs, SDKs, or best practices.",
                    "running",
                )
                try:
                    response = self.search_client.search_web(
                        prompt,
                        max_results=self.settings.search.default_max_results,
                    )
                    web_results = response.results
                    web_search_error = response.error
                    if web_results:
                        yield append_search_results([self._web_search_result(item, index) for index, item in enumerate(web_results)])
                    if response.error and not web_results:
                        yield emit_step(
                            "web-search",
                            "Search the web",
                            "Checking external sources for the latest APIs, SDKs, or best practices.",
                            "failed",
                            started_at=web_started,
                            output=response.error,
                        )
                        response = None
                    if response is None:
                        pass
                    else:
                        yield emit_step(
                            "web-search",
                            "Search the web",
                            "Checking external sources for the latest APIs, SDKs, or best practices.",
                            "completed",
                            started_at=web_started,
                            output=f"{len(web_results)} web results",
                        )
                except Exception as exc:
                    web_search_error = str(exc)
                    yield emit_step(
                        "web-search",
                        "Search the web",
                        "Checking external sources for the latest APIs, SDKs, or best practices.",
                        "failed",
                        started_at=web_started,
                        output=web_search_error,
                    )

            planning_started = time.perf_counter()
            yield emit_step(
                "planning",
                "Draft implementation plan",
                "Combining context, skills, and search results into a concrete plan.",
                "running",
            )
            plan = self.planning_agent.build_plan(
                prompt,
                knowledge_base=None,
                search_client=None,
                skill_registry=None,
                local_snippets=local_snippets,
                matched_skills=matched_skills,
                web_results=web_results,
                conversation_history=history,
            )
            plan = self.project_generator.normalize_plan(prompt, plan)
            yield emit_step(
                "planning",
                "Draft implementation plan",
                "Combining context, skills, and search results into a concrete plan.",
                "completed",
                started_at=planning_started,
                output=plan.summary,
            )

            if save_skill_name:
                note = self._build_skill_note(save_skill_name, prompt, plan)
                saved_skill_path = str(self.skill_registry.save(note))

            if generate_output_dir is not None:
                generation_started = time.perf_counter()
                yield emit_step(
                    "generation",
                    "Generate project files",
                    "Writing the planned files into the output directory.",
                    "running",
                )
                generation = self.project_generator.generate_project(
                    prompt,
                    plan,
                    output_dir=generate_output_dir,
                    on_file_written=lambda item: None,
                )
                for file_item in generation.files:
                    yield {
                        "type": "file",
                        "file": self._generated_file_node(file_item),
                    }
                yield emit_step(
                    "generation",
                    "Generate project files",
                    "Writing the planned files into the output directory.",
                    "completed",
                    started_at=generation_started,
                    output=f"{len(generation.files)} files written",
                )

            result = self._build_prompt_result(
                session_id=session_id,
                plan=plan,
                generation=generation,
                saved_skill_path=saved_skill_path,
                web_search_attempted=web_search_attempted,
                web_search_error=web_search_error,
            )
            self._persist_turn(session_id, prompt, result)

            for chunk in self._chunk_content(self._render_assistant_message(result)):
                yield {"type": "content", "content": chunk}
            yield {"type": "complete", "summary": result.summary}
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}

    def _build_plan(
        self,
        prompt: str,
        session_id: str | None,
    ) -> tuple[AgentPlan, bool, str | None]:
        history = self._conversation_history(session_id)
        plan = self.planning_agent.build_plan(
            prompt,
            knowledge_base=self.knowledge_base,
            search_client=self.search_client,
            skill_registry=self.skill_registry,
            conversation_history=history,
        )
        normalizer = getattr(self.project_generator, "normalize_plan", None)
        normalized_plan = normalizer(prompt, plan) if callable(normalizer) else plan
        return normalized_plan, normalized_plan.web_search_attempted, normalized_plan.web_search_error

    def _conversation_history(self, session_id: str | None) -> list[object]:
        if not session_id:
            return []
        return self.session_store.build_conversation_history(session_id, limit=6)

    def _build_prompt_result(
        self,
        *,
        session_id: str | None,
        plan: AgentPlan,
        generation: GenerationResult | None,
        saved_skill_path: str | None,
        web_search_attempted: bool,
        web_search_error: str | None,
    ) -> PromptResult:
        return PromptResult(
            session_id=session_id,
            summary=plan.summary,
            planned_files=plan.planned_files,
            implementation_steps=plan.implementation_steps,
            retrieved_sources=[snippet.source_name for snippet in plan.local_snippets],
            matched_skills=[note.name for note in plan.matched_skills],
            web_results=plan.web_results,
            web_search_attempted=web_search_attempted,
            agent_used_model=plan.used_model,
            generation_output_dir=generation.output_dir if generation is not None else None,
            generated_files=[item.path for item in generation.files] if generation is not None else None,
            generated_created_files=[item.path for item in generation.files if not item.existed_before] if generation is not None else None,
            generated_modified_files=[item.path for item in generation.files if item.existed_before] if generation is not None else None,
            generation_used_model=generation.used_model if generation is not None else False,
            saved_skill_path=saved_skill_path,
            web_search_error=web_search_error,
            agent_error=plan.model_error,
            generation_error=generation.model_error if generation is not None else None,
        )

    def _persist_turn(self, session_id: str | None, prompt: str, result: PromptResult) -> None:
        if not session_id:
            return
        self.session_store.append_turn(
            session_id,
            SessionTurn(
                turn_id=re.sub(r"[^a-zA-Z0-9]+", "-", prompt.strip().lower()).strip("-") or "turn",
                created_at=self._timestamp(),
                prompt=prompt,
                assistant_summary=result.summary,
                planned_files=result.planned_files,
                implementation_steps=result.implementation_steps,
                matched_skills=result.matched_skills,
                retrieved_sources=result.retrieved_sources,
                web_results=[
                    {
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                        "score": item.score,
                    }
                    for item in result.web_results
                ],
                web_search_attempted=result.web_search_attempted,
                web_search_error=result.web_search_error,
                agent_used_model=result.agent_used_model,
                agent_error=result.agent_error,
                generation_output_dir=result.generation_output_dir,
                generated_files=result.generated_files or [],
                generated_created_files=result.generated_created_files or [],
                generated_modified_files=result.generated_modified_files or [],
                generation_used_model=result.generation_used_model,
                generation_error=result.generation_error,
                saved_skill_path=result.saved_skill_path,
            ),
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

    def _should_search_web(self, prompt: str) -> bool:
        return should_search_web(prompt)

    @staticmethod
    def _local_search_result(snippet: KnowledgeSnippet) -> dict[str, object]:
        return {
            "id": f"local-{snippet.source_name}",
            "title": snippet.source_name,
            "content": snippet.excerpt,
            "source": "local",
            "score": float(snippet.score),
        }

    @staticmethod
    def _skill_search_result(note: SkillNote) -> dict[str, object]:
        return {
            "id": f"skill-{(note.slug or note.name).lower()}",
            "title": note.name,
            "content": note.summary,
            "source": "skill",
            "score": 0.8,
        }

    @staticmethod
    def _web_search_result(item: SearchResult, index: int) -> dict[str, object]:
        return {
            "id": f"web-{index}",
            "title": item.title,
            "content": item.snippet,
            "source": "web",
            "score": float(item.score or 0.6),
            "url": item.url,
        }

    @staticmethod
    def _generated_file_node(item: GeneratedFile) -> dict[str, object]:
        return {
            "name": Path(item.path).name,
            "path": item.path,
            "type": "file",
            "status": "modified" if item.existed_before else "new",
        }

    @staticmethod
    def _render_assistant_message(result: PromptResult) -> str:
        parts = [result.summary, "", "Planned files:"]
        parts.extend(f"- {path}" for path in result.planned_files)
        parts.append("")
        parts.append("Implementation steps:")
        parts.extend(f"- {step}" for step in result.implementation_steps)
        if result.web_search_error:
            parts.extend(["", f"Web search warning: {result.web_search_error}"])
        if result.generation_error:
            parts.extend(["", f"Generation warning: {result.generation_error}"])
        return "\n".join(parts)

    @staticmethod
    def _chunk_content(text: str, chunk_size: int = 120) -> Iterator[str]:
        if not text:
            return
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
