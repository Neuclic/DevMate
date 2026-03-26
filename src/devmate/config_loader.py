"""Load structured settings from TOML configuration files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError(
        "Python 3.11+ is required to read TOML with the standard library. "
        "This project targets Python 3.13."
    ) from exc


@dataclass(frozen=True)
class AppSection:
    """Runtime application settings."""

    project_name: str
    docs_dir: str
    log_level: str


@dataclass(frozen=True)
class ModelSection:
    """Model provider settings."""

    ai_base_url: str
    api_key: str
    model_name: str
    embedding_model_name: str


@dataclass(frozen=True)
class SearchSection:
    """Search provider settings."""

    tavily_api_key: str


@dataclass(frozen=True)
class McpSection:
    """MCP transport settings."""

    server_url: str
    transport: str


@dataclass(frozen=True)
class RagSection:
    """RAG settings."""

    provider: str
    collection_name: str
    top_k: int


@dataclass(frozen=True)
class LangSmithSection:
    """Observability settings."""

    langchain_tracing_v2: bool
    langchain_api_key: str


@dataclass(frozen=True)
class SkillsSection:
    """Skill storage settings."""

    skills_dir: str


@dataclass(frozen=True)
class AppSettings:
    """All application settings."""

    app: AppSection
    model: ModelSection
    search: SearchSection
    mcp: McpSection
    rag: RagSection
    langsmith: LangSmithSection
    skills: SkillsSection


def _read_toml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_settings(path: Path) -> AppSettings:
    """Load application settings from a TOML file."""
    data = _read_toml(path)

    app = data["app"]
    model = data["model"]
    search = data["search"]
    mcp = data["mcp"]
    rag = data["rag"]
    langsmith = data["langsmith"]
    skills = data["skills"]

    return AppSettings(
        app=AppSection(
            project_name=app["project_name"],
            docs_dir=app["docs_dir"],
            log_level=app["log_level"],
        ),
        model=ModelSection(
            ai_base_url=model["ai_base_url"],
            api_key=model["api_key"],
            model_name=model["model_name"],
            embedding_model_name=model["embedding_model_name"],
        ),
        search=SearchSection(
            tavily_api_key=search["tavily_api_key"],
        ),
        mcp=McpSection(
            server_url=mcp["server_url"],
            transport=mcp["transport"],
        ),
        rag=RagSection(
            provider=rag["provider"],
            collection_name=rag["collection_name"],
            top_k=rag["top_k"],
        ),
        langsmith=LangSmithSection(
            langchain_tracing_v2=langsmith["langchain_tracing_v2"],
            langchain_api_key=langsmith["langchain_api_key"],
        ),
        skills=SkillsSection(
            skills_dir=skills["skills_dir"],
        ),
    )
