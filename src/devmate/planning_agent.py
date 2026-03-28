"""LangChain planning agent with tool-driven context gathering."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langsmith.run_helpers import traceable
from pydantic import BaseModel, Field

from devmate.config_loader import AppSettings
from devmate.mcp_client import SearchMcpClient, SearchResult
from devmate.rag_pipeline import KnowledgeBasePipeline, KnowledgeSnippet
from devmate.search_policy import should_search_web
from devmate.session_store import ConversationTurn
from devmate.skill_registry import SkillNote, SkillRegistry

LOGGER = logging.getLogger(__name__)


class PlanResponse(BaseModel):
    """Structured plan returned by the LangChain agent."""

    summary: str = Field(description="One short sentence summarizing the plan.")
    planned_files: list[str] = Field(
        description="Repo-relative file paths that should be edited or created next."
    )
    implementation_steps: list[str] = Field(
        description="Three to six short actionable implementation steps."
    )


@dataclass
class ToolCapture:
    """Collected retrieval context used during one agent run."""

    local_snippets: list[KnowledgeSnippet] = field(default_factory=list)
    matched_skills: list[SkillNote] = field(default_factory=list)
    web_results: list[SearchResult] = field(default_factory=list)
    web_search_attempted: bool = False
    web_search_error: str | None = None


@dataclass(frozen=True)
class AgentPlan:
    """Structured implementation plan returned by the planning agent."""

    summary: str
    planned_files: list[str]
    implementation_steps: list[str]
    used_model: bool
    local_snippets: list[KnowledgeSnippet] = field(default_factory=list)
    matched_skills: list[SkillNote] = field(default_factory=list)
    web_results: list[SearchResult] = field(default_factory=list)
    web_search_attempted: bool = False
    web_search_error: str | None = None
    model_error: str | None = None


class PlanningAgent:
    """Generate a concrete implementation plan from retrieved project context."""

    def __init__(self, settings: AppSettings, model: ChatOpenAI | None = None) -> None:
        self.settings = settings
        self._model = model

    @traceable(run_type="chain", name="devmate_build_plan")
    def build_plan(
        self,
        prompt: str,
        *,
        knowledge_base: KnowledgeBasePipeline | None = None,
        search_client: SearchMcpClient | None = None,
        skill_registry: SkillRegistry | None = None,
        local_snippets: list[KnowledgeSnippet] | None = None,
        matched_skills: list[SkillNote] | None = None,
        web_results: list[SearchResult] | None = None,
        conversation_history: list[ConversationTurn] | None = None,
    ) -> AgentPlan:
        """Build an implementation plan using tools when the model is available."""
        if not prompt.strip():
            return self._fallback_plan(
                prompt=prompt,
                local_snippets=local_snippets or [],
                matched_skills=matched_skills or [],
                web_results=web_results or [],
            )

        if self._model is None and not self._model_is_configured():
            LOGGER.info("Planning model is not configured. Falling back to heuristic plan.")
            heuristics = self._collect_heuristic_context(
                prompt,
                knowledge_base=knowledge_base,
                search_client=search_client,
                skill_registry=skill_registry,
                local_snippets=local_snippets,
                matched_skills=matched_skills,
                web_results=web_results,
            )
            return self._fallback_plan(
                prompt=prompt,
                local_snippets=heuristics.local_snippets,
                matched_skills=heuristics.matched_skills,
                web_results=heuristics.web_results,
                web_search_attempted=heuristics.web_search_attempted,
                web_search_error=heuristics.web_search_error,
            )

        if knowledge_base is None or search_client is None:
            LOGGER.info("Planning tools are unavailable. Using direct-context planning.")
            return self._build_plan_from_context(
                prompt,
                local_snippets=local_snippets or [],
                matched_skills=matched_skills or [],
                web_results=web_results or [],
                conversation_history=conversation_history or [],
            )

        capture = ToolCapture()
        agent = create_agent(
            model=self._get_model(),
            tools=self._build_tools(knowledge_base, search_client, skill_registry, capture),
            system_prompt=self._system_prompt(),
            name="devmate-planning-agent",
        )

        try:
            result = agent.invoke(
                {
                    "messages": self._build_agent_messages(
                        prompt,
                        conversation_history or [],
                    )
                }
            )
            text = self._extract_agent_text(result)
            structured = self._parse_plan_text(text)
            return AgentPlan(
                summary=structured.summary.strip(),
                planned_files=[item.strip() for item in structured.planned_files if item.strip()],
                implementation_steps=[
                    item.strip() for item in structured.implementation_steps if item.strip()
                ],
                used_model=True,
                local_snippets=capture.local_snippets,
                matched_skills=capture.matched_skills,
                web_results=capture.web_results,
                web_search_attempted=capture.web_search_attempted,
                web_search_error=capture.web_search_error,
            )
        except Exception as exc:
            LOGGER.warning("Planning model failed, using fallback plan: %s", exc)
            heuristics = self._collect_heuristic_context(
                prompt,
                knowledge_base=knowledge_base,
                search_client=search_client,
                skill_registry=skill_registry,
                local_snippets=local_snippets,
                matched_skills=matched_skills,
                web_results=web_results,
            )
            fallback = self._fallback_plan(
                prompt=prompt,
                local_snippets=heuristics.local_snippets,
                matched_skills=heuristics.matched_skills,
                web_results=heuristics.web_results,
                web_search_attempted=heuristics.web_search_attempted,
                web_search_error=heuristics.web_search_error,
            )
            return AgentPlan(
                summary=fallback.summary,
                planned_files=fallback.planned_files,
                implementation_steps=fallback.implementation_steps,
                used_model=False,
                local_snippets=fallback.local_snippets,
                matched_skills=fallback.matched_skills,
                web_results=fallback.web_results,
                web_search_attempted=fallback.web_search_attempted,
                web_search_error=fallback.web_search_error,
                model_error=str(exc),
            )

    def _build_plan_from_context(
        self,
        prompt: str,
        *,
        local_snippets: list[KnowledgeSnippet],
        matched_skills: list[SkillNote],
        web_results: list[SearchResult],
        conversation_history: list[ConversationTurn],
    ) -> AgentPlan:
        try:
            response = self._get_model().invoke(
                self._build_messages(
                    prompt,
                    local_snippets,
                    matched_skills,
                    web_results,
                    conversation_history,
                )
            )
            text = self._message_text(response.content)
            structured = self._parse_plan_text(text)
            return AgentPlan(
                summary=structured.summary,
                planned_files=structured.planned_files,
                implementation_steps=structured.implementation_steps,
                used_model=True,
                local_snippets=local_snippets,
                matched_skills=matched_skills,
                web_results=web_results,
                web_search_attempted=bool(web_results),
            )
        except Exception as exc:
            LOGGER.warning("Direct-context planning failed, using fallback plan: %s", exc)
            fallback = self._fallback_plan(
                prompt=prompt,
                local_snippets=local_snippets,
                matched_skills=matched_skills,
                web_results=web_results,
                web_search_attempted=bool(web_results),
            )
            return AgentPlan(
                summary=fallback.summary,
                planned_files=fallback.planned_files,
                implementation_steps=fallback.implementation_steps,
                used_model=False,
                local_snippets=fallback.local_snippets,
                matched_skills=fallback.matched_skills,
                web_results=fallback.web_results,
                web_search_attempted=fallback.web_search_attempted,
                web_search_error=fallback.web_search_error,
                model_error=str(exc),
            )

    def _get_model(self) -> ChatOpenAI:
        if self._model is None:
            self._model = ChatOpenAI(
                model=self.settings.model.model_name,
                api_key=self.settings.model.api_key,
                base_url=self.settings.model.ai_base_url,
                timeout=30.0,
                max_retries=1,
                temperature=0.1,
            )
        return self._model

    def _model_is_configured(self) -> bool:
        key = self.settings.model.api_key.strip()
        base_url = self.settings.model.ai_base_url.strip()
        model_name = self.settings.model.model_name.strip()
        if not key or not base_url or not model_name:
            return False
        return not key.lower().startswith("your_")

    def _build_tools(
        self,
        knowledge_base: KnowledgeBasePipeline,
        search_client: SearchMcpClient,
        skill_registry: SkillRegistry | None,
        capture: ToolCapture,
    ) -> list[object]:
        @tool
        def search_local_knowledge(query: str) -> str:
            """Search local project documentation and coding guidelines."""
            snippets = knowledge_base.search(query, limit=self.settings.rag.top_k)
            capture.local_snippets = snippets
            if not snippets:
                return "No local knowledge matches were found."
            return self._format_local_snippets(snippets)

        @tool
        def search_saved_skills(query: str) -> str:
            """Search saved successful task patterns and reusable skills."""
            if skill_registry is None:
                return "No saved skills registry is configured."
            notes = skill_registry.search(query, limit=3)
            capture.matched_skills = notes
            if not notes:
                return "No matching saved skills were found."
            return self._format_skills(notes)

        @tool
        def read_saved_skill(skill_name: str) -> str:
            """Read the full content of one saved skill after it has been selected."""
            if skill_registry is None:
                return "No saved skills registry is configured."
            note = skill_registry.load(skill_name)
            if note is None:
                return f"No saved skill named '{skill_name}' was found."
            if all(existing.name != note.name for existing in capture.matched_skills):
                capture.matched_skills.append(note)
            context = skill_registry.load_context(skill_name)
            return context or f"No detailed content was available for '{skill_name}'."

        @tool
        def search_web(query: str) -> str:
            """Search the web for latest external information, APIs, or best practices."""
            capture.web_search_attempted = True
            try:
                response = search_client.search_web(
                    query,
                    max_results=self.settings.search.default_max_results,
                )
            except Exception as exc:
                capture.web_search_error = str(exc)
                return f"Web search unavailable: {exc}"
            capture.web_results = response.results
            if response.error:
                capture.web_search_error = response.error
                if not response.results:
                    return f"Web search unavailable: {response.error}"
            if not response.results:
                return "Web search returned no results."
            return self._format_web_results(response.results)

        return [search_local_knowledge, search_saved_skills, read_saved_skill, search_web]

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are DevMate, a coding assistant planning agent. "
            "Use tools only when they materially improve the plan. "
            "If the user message is a follow-up, preserve continuity with the recent conversation. "
            "If the latest user request clearly asks for a different artifact, style, or domain, prioritize the latest request over earlier context. "
            "Use search_local_knowledge for local docs, templates, and coding guidelines. "
            "Use search_saved_skills to find prior task patterns, then use read_saved_skill on the best match before relying on it. "
            "Use search_web for latest external facts, best practices, libraries, or release notes. "
            "Do not call every tool by default. "
            "Return JSON only with the keys summary, planned_files, implementation_steps. "
            "planned_files must be repo-relative paths. "
            "implementation_steps must contain 3 to 6 short actionable strings."
        )

    @staticmethod
    def _build_messages(
        prompt: str,
        local_snippets: list[KnowledgeSnippet],
        matched_skills: list[SkillNote],
        web_results: list[SearchResult],
        conversation_history: list[ConversationTurn],
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                "You are DevMate, a planning agent for a coding assistant. "
                "Turn the user request plus retrieved context into a concrete implementation plan. "
                "If the latest user request conflicts with earlier session history, follow the latest explicit request. "
                "Return JSON only with the keys: summary, planned_files, implementation_steps. "
                "summary must be one short sentence. "
                "planned_files must be a list of repo-relative paths. "
                    "implementation_steps must be a list of 3 to 6 short actionable steps."
                ),
            },
            {
                "role": "user",
                "content": PlanningAgent._build_context(
                    prompt,
                    local_snippets,
                    matched_skills,
                    web_results,
                    conversation_history,
                ),
            },
        ]

    @staticmethod
    def _format_local_snippets(snippets: list[KnowledgeSnippet]) -> str:
        return "\n".join(
            f"- {snippet.source_name} | score={snippet.score:.4f} | {snippet.excerpt}"
            for snippet in snippets
        )

    @staticmethod
    def _format_skills(skills: list[SkillNote]) -> str:
        return "\n".join(
            (
                f"- {item.name} | {item.summary} | "
                f"keywords={', '.join(item.keywords) if item.keywords else 'none'} | "
                f"steps={'; '.join(item.steps)}"
            )
            for item in skills
        )

    @staticmethod
    def _format_web_results(results: list[SearchResult]) -> str:
        return "\n".join(f"- {item.title} | {item.url} | {item.snippet}" for item in results)

    @staticmethod
    def _build_context(
        prompt: str,
        local_snippets: list[KnowledgeSnippet],
        matched_skills: list[SkillNote],
        web_results: list[SearchResult],
        conversation_history: list[ConversationTurn],
    ) -> str:
        history_block = "\n".join(
            f"- User: {turn.prompt}\n  Assistant: {turn.assistant_summary}"
            for turn in conversation_history
        ) or "- none"
        local_block = "\n".join(
            f"- {snippet.source_name}: {snippet.excerpt}" for snippet in local_snippets
        ) or "- none"
        skill_block = "\n".join(
            f"- {item.name}: {item.summary} | steps: {'; '.join(item.steps)}"
            for item in matched_skills
        ) or "- none"
        web_block = "\n".join(
            f"- {item.title} | {item.url} | {item.snippet}" for item in web_results
        ) or "- none"
        return (
            f"Recent conversation history:\n{history_block}\n\n"
            f"User request:\n{prompt}\n\n"
            f"Local knowledge snippets:\n{local_block}\n\n"
            f"Matched saved skills:\n{skill_block}\n\n"
            f"Web results:\n{web_block}\n\n"
            "Generate the next implementation plan for this repository."
        )

    @staticmethod
    def _build_agent_messages(
        prompt: str,
        conversation_history: list[ConversationTurn],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for turn in conversation_history:
            messages.append({"role": "user", "content": turn.prompt})
            messages.append({"role": "assistant", "content": turn.assistant_summary})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _message_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                else:
                    text = getattr(item, "text", None)
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts).strip()
        return str(content)

    @classmethod
    def _extract_agent_text(cls, result: dict[str, object]) -> str:
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            content = getattr(messages[-1], "content", None)
            if content is not None:
                text = cls._message_text(content)
                if text.strip():
                    return text
        output = result.get("output")
        if output is not None:
            text = cls._message_text(output)
            if text.strip():
                return text
        raise ValueError("LangChain agent did not return a readable final message.")

    @classmethod
    def _parse_plan_text(cls, text: str) -> AgentPlan:
        import json

        payload = json.loads(cls._extract_json_blob(text))
        summary = str(payload["summary"]).strip()
        planned_files = cls._ensure_string_list(payload.get("planned_files", []))
        implementation_steps = cls._ensure_string_list(
            payload.get("implementation_steps", [])
        )
        if not summary:
            raise ValueError("Planning response summary is empty.")
        if not planned_files:
            raise ValueError("Planning response planned_files is empty.")
        if not implementation_steps:
            raise ValueError("Planning response implementation_steps is empty.")
        return AgentPlan(
            summary=summary,
            planned_files=planned_files,
            implementation_steps=implementation_steps,
            used_model=True,
        )

    @staticmethod
    def _extract_json_blob(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                stripped = "\n".join(lines[1:-1]).strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Planning response did not contain JSON.")
        return stripped[start : end + 1]

    @staticmethod
    def _ensure_string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("Planning response field must be a list.")
        return [str(item).strip() for item in value if str(item).strip()]

    def _collect_heuristic_context(
        self,
        prompt: str,
        *,
        knowledge_base: KnowledgeBasePipeline | None,
        search_client: SearchMcpClient | None,
        skill_registry: SkillRegistry | None,
        local_snippets: list[KnowledgeSnippet] | None,
        matched_skills: list[SkillNote] | None,
        web_results: list[SearchResult] | None,
    ) -> ToolCapture:
        capture = ToolCapture(
            local_snippets=list(local_snippets or []),
            matched_skills=list(matched_skills or []),
            web_results=list(web_results or []),
        )
        if not capture.local_snippets and knowledge_base is not None:
            capture.local_snippets = knowledge_base.search(prompt, limit=self.settings.rag.top_k)
        if not capture.matched_skills and skill_registry is not None:
            capture.matched_skills = skill_registry.search(prompt, limit=3)
        if not capture.web_results and search_client is not None and self._should_search_web(prompt):
            capture.web_search_attempted = True
            try:
                response = search_client.search_web(
                    prompt,
                    max_results=self.settings.search.default_max_results,
                )
                capture.web_results = response.results
                capture.web_search_error = response.error
            except Exception as exc:
                capture.web_search_error = str(exc)
                LOGGER.warning("Heuristic web search failed for prompt '%s': %s", prompt, exc)
        return capture

    @staticmethod
    def _should_search_web(prompt: str) -> bool:
        return should_search_web(prompt)

    @staticmethod
    def _fallback_plan(
        prompt: str,
        *,
        local_snippets: list[KnowledgeSnippet],
        matched_skills: list[SkillNote],
        web_results: list[SearchResult],
        web_search_attempted: bool = False,
        web_search_error: str | None = None,
    ) -> AgentPlan:
        focus = PlanningAgent._infer_focus(prompt)
        planned_files = [
            "src/devmate/agent_runtime.py",
            "src/devmate/rag_pipeline.py",
            "src/devmate/mcp_client.py",
            "tests/test_agent_runtime.py",
        ]
        if matched_skills:
            planned_files.append(".skills/")
        if focus == "frontend":
            planned_files.extend(
                [
                    "docs/internal_frontend_guidelines.md",
                    "docs/architecture.md",
                ]
            )
        elif focus == "api":
            planned_files.append("docs/architecture.md")

        summary = (
            "Prepared an initial implementation plan from "
            f"{len(local_snippets)} local snippets, "
            f"{len(matched_skills)} matched skills and {len(web_results)} web results."
        )
        steps = [
            "Review the prompt and extracted context to confirm the target feature scope.",
            "Reuse any matching saved skill before updating runtime and integration modules.",
            "Implement the requested behavior in the relevant modules and configuration files.",
            "Add or adjust tests to cover the new execution path and failure cases.",
            "Run the local verification commands and capture any follow-up gaps.",
        ]
        return AgentPlan(
            summary=summary,
            planned_files=planned_files,
            implementation_steps=steps,
            used_model=False,
            local_snippets=local_snippets,
            matched_skills=matched_skills,
            web_results=web_results,
            web_search_attempted=web_search_attempted,
            web_search_error=web_search_error,
        )

    @staticmethod
    def _infer_focus(prompt: str) -> str:
        lowered = prompt.lower()
        if any(word in lowered for word in {"site", "website", "ui", "frontend", "page"}):
            return "frontend"
        if any(word in lowered for word in {"api", "fastapi", "service", "backend"}):
            return "api"
        return "general"
