"""Tests for prompt-time MCP search integration."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import load_settings
from devmate.mcp_client import SearchResponse, SearchResult
from devmate.planning_agent import AgentPlan
from devmate.project_generator import GeneratedFile, GenerationResult
from devmate.skill_registry import SkillNote, SkillRegistry


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class SuccessfulSearchClient:
    """Fake MCP client used to verify prompt-time search."""

    def search_web(self, query: str, *, max_results: int = 5) -> SearchResponse:
        del max_results
        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    title="FastAPI release notes",
                    url="https://fastapi.tiangolo.com/release-notes/",
                    snippet="Release notes",
                )
            ],
        )


class FailingSearchClient:
    """Fake MCP client used to verify graceful degradation."""

    def search_web(self, query: str, *, max_results: int = 5) -> SearchResponse:
        del query, max_results
        raise RuntimeError("server unavailable")


class FakePlanningAgent:
    """Fake planning agent used to isolate runtime wiring."""

    def build_plan(self, prompt: str, **kwargs: object) -> AgentPlan:
        search_client = kwargs.get("search_client")
        knowledge_base = kwargs.get("knowledge_base")
        skill_registry = kwargs.get("skill_registry")
        local_snippets = knowledge_base.search(prompt, limit=4) if knowledge_base else []
        matched_skills = skill_registry.search(prompt, limit=3) if skill_registry else []
        web_results: list[SearchResult] = []
        web_search_attempted = False
        web_search_error: str | None = None

        if search_client is not None:
            web_search_attempted = True
            try:
                response = search_client.search_web(prompt, max_results=5)
                web_results = response.results
            except Exception as exc:
                web_search_error = str(exc)

        return AgentPlan(
            summary=f"Plan for: {prompt}",
            planned_files=["src/devmate/agent_runtime.py", "tests/test_agent_runtime.py"],
            implementation_steps=[
                "Collect the prompt context.",
                "Produce the next code changes.",
                "Verify the behavior with tests.",
            ],
            used_model=False,
            local_snippets=local_snippets,
            matched_skills=matched_skills,
            web_results=web_results,
            web_search_attempted=web_search_attempted,
            web_search_error=web_search_error,
        )


class FakeProjectGenerator:
    """Fake project generator used to verify runtime generation wiring."""

    def generate_project(self, prompt: str, plan: AgentPlan, output_dir: Path) -> GenerationResult:
        del prompt, plan
        return GenerationResult(
            output_dir=str(output_dir),
            files=[
                GeneratedFile(path="index.html", content="<h1>Demo</h1>", existed_before=False),
                GeneratedFile(path="README.md", content="# Demo", existed_before=True),
            ],
            used_model=False,
        )


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def _write_config(path: Path, *, docs_dir: Path, skills_dir: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[app]",
                'project_name = "DevMate"',
                f'docs_dir = "{docs_dir.as_posix()}"',
                'log_level = "INFO"',
                "",
                "[model]",
                'ai_base_url = "https://api.minimax.io/v1"',
                'api_key = "test"',
                'model_name = "MiniMax-M2"',
                'embedding_base_url = "https://api.minimax.io/v1"',
                'embedding_api_key = "test"',
                'embedding_model_name = ""',
                "",
                "[search]",
                'tavily_api_key = "test"',
                "default_max_results = 5",
                "request_timeout_seconds = 20.0",
                "",
                "[mcp]",
                'server_url = "http://localhost:8001/mcp"',
                'transport = "streamable_http"',
                "tool_timeout_seconds = 30.0",
                "healthcheck_timeout_seconds = 5.0",
                "",
                "[rag]",
                'provider = "chromadb"',
                'collection_name = "devmate-docs"',
                'persist_directory = ".chroma/test-agent-runtime"',
                "chunk_size = 400",
                "chunk_overlap = 40",
                "top_k = 4",
                "",
                "[langsmith]",
                "langchain_tracing_v2 = true",
                'langchain_api_key = "test"',
                "",
                "[skills]",
                f'skills_dir = "{skills_dir.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_prompt_triggers_web_search() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        (docs_dir / "guide.md").write_text(
            "FastAPI project guidelines and release process.",
            encoding="utf-8",
        )
        SkillRegistry(skills_dir).save(
            SkillNote(
                name="Build API Service",
                summary="Use this when the prompt asks for an API backend.",
                steps=["Define routes.", "Add tests."],
                keywords=["fastapi", "api", "backend"],
            )
        )
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)

        settings = load_settings(config_path)
        runtime = DevMateRuntime(
            settings,
            search_client=SuccessfulSearchClient(),
            planning_agent=FakePlanningAgent(),
        )

        result = runtime.handle_prompt("latest FastAPI release notes")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.web_search_attempted is True
    assert result.summary == "Plan for: latest FastAPI release notes"
    assert len(result.web_results) == 1
    assert result.web_results[0].title == "FastAPI release notes"
    assert result.matched_skills == ["Build API Service"]
    assert result.planned_files == [
        "src/devmate/agent_runtime.py",
        "tests/test_agent_runtime.py",
    ]
    assert result.implementation_steps[0] == "Collect the prompt context."
    assert result.agent_used_model is False


def test_prompt_gracefully_handles_web_search_failure() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        (docs_dir / "guide.md").write_text(
            "FastAPI project guidelines.",
            encoding="utf-8",
        )
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)

        settings = load_settings(config_path)
        runtime = DevMateRuntime(
            settings,
            search_client=FailingSearchClient(),
            planning_agent=FakePlanningAgent(),
        )

        result = runtime.handle_prompt("latest FastAPI release notes")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.web_search_attempted is True
    assert result.web_results == []
    assert result.web_search_error == "server unavailable"
    assert result.summary == "Plan for: latest FastAPI release notes"


def test_prompt_can_save_skill_note() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        (docs_dir / "guide.md").write_text("Frontend layout guidance.", encoding="utf-8")
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)

        settings = load_settings(config_path)
        runtime = DevMateRuntime(
            settings,
            search_client=SuccessfulSearchClient(),
            planning_agent=FakePlanningAgent(),
        )

        result = runtime.handle_prompt(
            "build a responsive map website",
            save_skill_name="Build Map Website",
        )
        saved_path = Path(result.saved_skill_path or "")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.saved_skill_path is not None
    assert saved_path.name == "SKILL.md"
    assert saved_path.parent.name == "build-map-website"


def test_prompt_can_generate_project_files() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        docs_dir = root / "docs"
        skills_dir = root / ".skills"
        docs_dir.mkdir()
        skills_dir.mkdir()
        (docs_dir / "guide.md").write_text("Frontend layout guidance.", encoding="utf-8")
        _write_config(config_path, docs_dir=docs_dir, skills_dir=skills_dir)

        settings = load_settings(config_path)
        runtime = DevMateRuntime(
            settings,
            search_client=SuccessfulSearchClient(),
            planning_agent=FakePlanningAgent(),
            project_generator=FakeProjectGenerator(),
        )

        result = runtime.handle_prompt(
            "build a responsive map website",
            generate_output_dir=root / "out",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.generation_output_dir is not None
    assert result.generated_files == ["index.html", "README.md"]
    assert result.generated_created_files == ["index.html"]
    assert result.generated_modified_files == ["README.md"]
    assert result.generation_used_model is False
