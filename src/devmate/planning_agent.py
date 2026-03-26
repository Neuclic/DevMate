"""Planning agent that turns retrieved context into an implementation plan."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from devmate.config_loader import AppSettings
from devmate.mcp_client import SearchResult
from devmate.rag_pipeline import KnowledgeSnippet

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentPlan:
    """Structured implementation plan returned by the planning agent."""

    summary: str
    planned_files: list[str]
    implementation_steps: list[str]
    used_model: bool
    model_error: str | None = None


class PlanningAgent:
    """Generate a concrete implementation plan from retrieved project context."""

    def __init__(self, settings: AppSettings, model: ChatOpenAI | None = None) -> None:
        self.settings = settings
        self._model = model

    def build_plan(
        self,
        prompt: str,
        *,
        local_snippets: list[KnowledgeSnippet],
        web_results: list[SearchResult],
    ) -> AgentPlan:
        """Build an implementation plan using the configured model when possible."""
        if not prompt.strip():
            return self._fallback_plan(
                prompt=prompt,
                local_snippets=local_snippets,
                web_results=web_results,
            )

        if self._model is None and not self._model_is_configured():
            LOGGER.info("Planning model is not configured. Falling back to heuristic plan.")
            return self._fallback_plan(
                prompt=prompt,
                local_snippets=local_snippets,
                web_results=web_results,
            )

        try:
            response = self._get_model().invoke(self._build_messages(prompt, local_snippets, web_results))
            text = self._message_text(response.content)
            plan = self._parse_plan_text(text)
            return AgentPlan(
                summary=plan.summary,
                planned_files=plan.planned_files,
                implementation_steps=plan.implementation_steps,
                used_model=True,
            )
        except Exception as exc:
            LOGGER.warning("Planning model failed, using fallback plan: %s", exc)
            fallback = self._fallback_plan(
                prompt=prompt,
                local_snippets=local_snippets,
                web_results=web_results,
            )
            return AgentPlan(
                summary=fallback.summary,
                planned_files=fallback.planned_files,
                implementation_steps=fallback.implementation_steps,
                used_model=False,
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

    def _build_messages(
        self,
        prompt: str,
        local_snippets: list[KnowledgeSnippet],
        web_results: list[SearchResult],
    ) -> list[SystemMessage | HumanMessage]:
        system_message = SystemMessage(
            content=(
                "You are DevMate, a planning agent for a coding assistant. "
                "Turn the user request plus retrieved context into a concrete implementation plan. "
                "Return JSON only with the keys: summary, planned_files, implementation_steps. "
                "summary must be one short sentence. "
                "planned_files must be a list of repo-relative paths. "
                "implementation_steps must be a list of 3 to 6 short actionable steps."
            )
        )
        human_message = HumanMessage(
            content=self._build_context(prompt, local_snippets, web_results)
        )
        return [system_message, human_message]

    @staticmethod
    def _build_context(
        prompt: str,
        local_snippets: list[KnowledgeSnippet],
        web_results: list[SearchResult],
    ) -> str:
        local_block = "\n".join(
            f"- {snippet.source_name}: {snippet.excerpt}"
            for snippet in local_snippets
        ) or "- none"
        web_block = "\n".join(
            f"- {item.title} | {item.url} | {item.snippet}"
            for item in web_results
        ) or "- none"
        return (
            f"User request:\n{prompt}\n\n"
            f"Local knowledge snippets:\n{local_block}\n\n"
            f"Web results:\n{web_block}\n\n"
            "Generate the next implementation plan for this repository."
        )

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
    def _parse_plan_text(cls, text: str) -> AgentPlan:
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

    @staticmethod
    def _fallback_plan(
        prompt: str,
        *,
        local_snippets: list[KnowledgeSnippet],
        web_results: list[SearchResult],
    ) -> AgentPlan:
        focus = PlanningAgent._infer_focus(prompt)
        planned_files = [
            "src/devmate/agent_runtime.py",
            "src/devmate/rag_pipeline.py",
            "src/devmate/mcp_client.py",
            "tests/test_agent_runtime.py",
        ]
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
            f"{len(local_snippets)} local snippets and {len(web_results)} web results."
        )
        steps = [
            "Review the prompt and extracted context to confirm the target feature scope.",
            "Update the relevant runtime and integration modules for the requested behavior.",
            "Add or adjust tests to cover the new execution path and failure cases.",
            "Run the local verification commands and capture any follow-up gaps.",
        ]
        return AgentPlan(
            summary=summary,
            planned_files=planned_files,
            implementation_steps=steps,
            used_model=False,
        )

    @staticmethod
    def _infer_focus(prompt: str) -> str:
        lowered = prompt.lower()
        if any(word in lowered for word in {"site", "website", "ui", "frontend", "page"}):
            return "frontend"
        if any(word in lowered for word in {"api", "fastapi", "service", "backend"}):
            return "api"
        return "general"
