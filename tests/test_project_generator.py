"""Tests for project file generation."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from devmate.config_loader import load_settings
from devmate.planning_agent import AgentPlan
from devmate.project_generator import ProjectGenerator


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


class FakeMessage:
    """Minimal message wrapper used by the fake model."""

    def __init__(self, content: object) -> None:
        self.content = content


class FakeModel:
    """Fake model that returns a fixed JSON payload."""

    def __init__(self, file_contents: dict[str, str]) -> None:
        self.file_contents = file_contents

    def invoke(self, messages: object) -> FakeMessage:
        prompt = str(messages[-1]["content"])
        marker = "Target file:\n"
        start = prompt.find(marker)
        if start == -1:
            return FakeMessage("")
        start += len(marker)
        end = prompt.find("\n", start)
        path = prompt[start:end].strip()
        return FakeMessage(self.file_contents.get(path, ""))


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def _write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[app]",
                'project_name = "DevMate"',
                'docs_dir = "docs"',
                'log_level = "INFO"',
                "",
                "[model]",
                'ai_base_url = "https://api.minimaxi.com/v1"',
                'api_key = "test"',
                'model_name = "MiniMax-M2"',
                'embedding_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"',
                'embedding_api_key = "test"',
                'embedding_model_name = "text-embedding-v4"',
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
                'persist_directory = ".chroma/test-generator"',
                "chunk_size = 400",
                "chunk_overlap = 40",
                "top_k = 4",
                "",
                "[langsmith]",
                "langchain_tracing_v2 = true",
                'langchain_api_key = "test"',
                "",
                "[skills]",
                'skills_dir = ".skills"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _plan() -> AgentPlan:
    return AgentPlan(
        summary="Build a map website.",
        planned_files=["index.html", "css/styles.css", "README.md"],
        implementation_steps=[
            "Create the page shell.",
            "Add responsive styles.",
            "Document how to run the site.",
        ],
        used_model=True,
    )


def test_project_generator_uses_template_fallback_when_model_is_not_configured() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        object.__setattr__(settings.model, 'api_key', 'your_minimax_api_key_here')
        generator = ProjectGenerator(settings)

        result = generator.generate_project(
            "build a responsive map website",
            _plan(),
            output_dir=root / "out",
        )

        index_content = (root / "out" / "index.html").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.used_model is False
    assert len(result.files) == 4
    assert [item.path for item in result.files] == [
        "index.html",
        "css/styles.css",
        "README.md",
        "js/app.js",
    ]
    assert "Trail Atlas" in index_content


def test_project_generator_writes_model_generated_files() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        model = FakeModel(
            {
                "index.html": "<h1>Hello</h1>",
                "README.md": "# Demo",
            }
        )
        generator = ProjectGenerator(settings, model=model)

        result = generator.generate_project(
            "build a responsive map website",
            _plan(),
            output_dir=root / "out",
        )

        index_content = (root / "out" / "index.html").read_text(encoding="utf-8")
        css_content = (root / "out" / "css" / "styles.css").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.used_model is True
    assert "<h1>Hello</h1>" in index_content
    assert "background" in css_content


def test_project_generator_marks_existing_files_as_modified() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        object.__setattr__(settings.model, 'api_key', 'your_minimax_api_key_here')
        generator = ProjectGenerator(settings)
        output_dir = root / "out"
        output_dir.mkdir()
        (output_dir / "README.md").write_text("# Existing\n", encoding="utf-8")

        result = generator.generate_project(
            "update the generated project readme",
            _plan(),
            output_dir=output_dir,
        )

        readme_content = (output_dir / "README.md").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    modified = [item.path for item in result.files if item.existed_before]
    assert modified == ["README.md"]
    assert "DevMate Update" in readme_content

def test_browser_game_prompt_expands_single_file_plan_into_runnable_scaffold() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        object.__setattr__(settings.model, "api_key", "your_minimax_api_key_here")
        generator = ProjectGenerator(settings)
        plan = AgentPlan(
            summary="Build a Flappy Bird web game.",
            planned_files=["index.html"],
            implementation_steps=["Create a game page."],
            used_model=False,
        )

        result = generator.generate_project(
            "???? flappy bird ? web ??",
            plan,
            output_dir=root / "out",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert [item.path for item in result.files] == [
        "index.html",
        "styles.css",
        "js/main.js",
        "js/game.js",
        "README.md",
    ]


def test_browser_game_prompt_keeps_existing_web_scaffold_paths_without_duplication() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        generator = ProjectGenerator(settings)
        plan = AgentPlan(
            summary="Build a Flappy Bird web game.",
            planned_files=[
                "flappy-bird/index.html",
                "flappy-bird/style.css",
                "flappy-bird/game.js",
            ],
            implementation_steps=["Create the scaffold."],
            used_model=True,
        )

        normalized = generator.normalize_plan("build a flappy bird web game", plan)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert normalized.planned_files == [
        "flappy-bird/index.html",
        "flappy-bird/style.css",
        "flappy-bird/game.js",
        "README.md",
    ]


def test_static_visual_prompt_does_not_fall_back_to_browser_game() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        object.__setattr__(settings.model, "api_key", "your_minimax_api_key_here")
        generator = ProjectGenerator(settings)
        plan = AgentPlan(
            summary="Create a static front-end visual page.",
            planned_files=["index.html"],
            implementation_steps=["Create the page."],
            used_model=False,
        )

        normalized = generator.normalize_plan(
            "写一个静态的前端界面绘制一个美少女，拥有全世界都想守护的笑容",
            plan,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert normalized.planned_files == [
        "index.html",
        "styles.css",
        "js/app.js",
        "README.md",
    ]
    assert all("Flappy Bird" not in step for step in normalized.implementation_steps)


def test_static_site_template_respects_planned_asset_paths() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        object.__setattr__(settings.model, "api_key", "your_minimax_api_key_here")
        generator = ProjectGenerator(settings)
        plan = AgentPlan(
            summary="Create a static poster page.",
            planned_files=["index.html", "css/style.css", "js/main.js", "README.md"],
            implementation_steps=["Create the page."],
            used_model=False,
        )

        result = generator.generate_project(
            "写一个静态的前端界面，展示一个拥有温暖笑容的美少女海报页",
            plan,
            output_dir=root / "out",
        )

        index_content = (root / "out" / "index.html").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.files[0].path == "index.html"
    assert 'href="css/style.css"' in index_content
    assert 'src="js/main.js"' in index_content


def test_project_generator_strips_think_blocks_and_file_headers_from_model_output() -> None:
    root = _make_test_root()
    try:
        config_path = root / "config.toml"
        _write_config(config_path)
        settings = load_settings(config_path)
        model = FakeModel(
            {
                "index.html": (
                    "<think>\nreasoning here\n</think>\n\n"
                    "index.html\n"
                    "<!DOCTYPE html>\n"
                    "<html><body><h1>Poster</h1></body></html>\n"
                    "css/style.css\n"
                    "body { color: red; }\n"
                ),
                "README.md": (
                    "<think>extra thoughts</think>\n"
                    "README.md\n"
                    "# Demo Poster\n\n"
                    "- Open index.html in a browser.\n"
                ),
            }
        )
        generator = ProjectGenerator(settings, model=model)
        plan = AgentPlan(
            summary="Create a static poster page.",
            planned_files=["index.html", "css/style.css", "js/main.js", "README.md"],
            implementation_steps=["Create the page."],
            used_model=True,
        )

        result = generator.generate_project(
            "build a static poster site",
            plan,
            output_dir=root / "out",
        )

        index_content = (root / "out" / "index.html").read_text(encoding="utf-8")
        readme_content = (root / "out" / "README.md").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert result.used_model is True
    assert "<think>" not in index_content
    assert "css/style.css" not in index_content
    assert index_content.startswith("<!DOCTYPE html>")
    assert "<think>" not in readme_content
    assert readme_content.startswith("# Demo Poster")
    assert "index.html" not in readme_content
