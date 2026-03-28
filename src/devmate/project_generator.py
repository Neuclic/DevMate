"""Generate project files from an implementation plan."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Generator
from dataclasses import dataclass, replace
from pathlib import Path

from langchain_openai import ChatOpenAI
from langsmith.run_helpers import traceable

from devmate.config_loader import AppSettings
from devmate.planning_agent import AgentPlan


@dataclass(frozen=True)
class GeneratedFile:
    """One generated file written to disk."""

    path: str
    content: str
    existed_before: bool = False


@dataclass(frozen=True)
class GenerationResult:
    """Summary of project generation output."""

    output_dir: str
    files: list[GeneratedFile]
    used_model: bool
    model_error: str | None = None


@dataclass(frozen=True)
class GenerationProgressEvent:
    """One incremental generation event emitted during file creation."""

    kind: str
    path: str
    existed_before: bool = False
    used_model: bool = False
    content_chunk: str | None = None
    message: str | None = None


class ProjectGenerator:
    """Generate a multi-file project from a prompt and plan."""

    def __init__(self, settings: AppSettings, model: ChatOpenAI | None = None) -> None:
        self.settings = settings
        self._model = model

    def normalize_plan(self, prompt: str, plan: AgentPlan) -> AgentPlan:
        """Expand weak single-file plans into runnable starter projects."""
        mode = self._infer_mode(prompt, plan.planned_files)
        planned_files = self._normalized_files(mode, plan.planned_files)
        implementation_steps = self._normalized_steps(mode, plan.implementation_steps)
        return replace(plan, planned_files=planned_files, implementation_steps=implementation_steps)

    @traceable(run_type="chain", name="generate_project_files")
    def generate_project(
        self,
        prompt: str,
        plan: AgentPlan,
        output_dir: Path,
        *,
        on_progress: Callable[[GenerationProgressEvent], None] | None = None,
        on_file_written: Callable[[GeneratedFile], None] | None = None,
    ) -> GenerationResult:
        """Write the generated project files to disk."""
        stream = self.generate_project_stream(
            prompt,
            plan,
            output_dir,
            on_file_written=on_file_written,
        )
        while True:
            try:
                event = next(stream)
            except StopIteration as stop:
                return stop.value
            if on_progress is not None:
                on_progress(event)

    @traceable(run_type="chain", name="generate_project_files_stream")
    def generate_project_stream(
        self,
        prompt: str,
        plan: AgentPlan,
        output_dir: Path,
        *,
        on_file_written: Callable[[GeneratedFile], None] | None = None,
    ) -> Generator[GenerationProgressEvent, None, GenerationResult]:
        """Yield generation progress while writing project files to disk."""
        normalized_plan = self.normalize_plan(prompt, plan)
        output_dir.mkdir(parents=True, exist_ok=True)
        existing_files = self._load_existing_files(output_dir, normalized_plan)
        generated_files: list[GeneratedFile] = []
        model_generated_count = 0
        model_errors: list[str] = []

        for path in normalized_plan.planned_files:
            existed_before = path in existing_files
            can_use_model = self._model_is_configured()
            yield GenerationProgressEvent(
                kind="started",
                path=path,
                existed_before=existed_before,
                used_model=can_use_model,
            )

            if can_use_model:
                try:
                    generated = yield from self._generate_single_file_with_model(
                        prompt,
                        normalized_plan,
                        path,
                        existing_files.get(path),
                        existed_before=existed_before,
                    )
                    model_generated_count += 1
                except Exception as exc:
                    model_errors.append(f"{path}: {exc}")
                    yield GenerationProgressEvent(
                        kind="fallback",
                        path=path,
                        existed_before=existed_before,
                        used_model=False,
                        message=str(exc),
                    )
                    generated = GeneratedFile(
                        path=path,
                        content=self._template_for_path(
                            path,
                            prompt,
                            normalized_plan,
                            existing_files.get(path),
                        ),
                        existed_before=existed_before,
                    )
            else:
                yield GenerationProgressEvent(
                    kind="fallback",
                    path=path,
                    existed_before=existed_before,
                    used_model=False,
                    message="Planning model is not configured for file generation.",
                )
                generated = GeneratedFile(
                    path=path,
                    content=self._template_for_path(
                        path,
                        prompt,
                        normalized_plan,
                        existing_files.get(path),
                    ),
                    existed_before=existed_before,
                )

            target = output_dir / generated.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(generated.content.rstrip() + "\n", encoding="utf-8")
            generated_files.append(generated)
            if on_file_written is not None:
                on_file_written(generated)
            yield GenerationProgressEvent(
                kind="completed",
                path=generated.path,
                existed_before=generated.existed_before,
                used_model=generated.path not in {item.split(":")[0] for item in model_errors},
            )

        model_error = "; ".join(model_errors) if model_errors else None
        return GenerationResult(
            output_dir=str(output_dir.resolve()),
            files=generated_files,
            used_model=model_generated_count > 0,
            model_error=model_error,
        )

    def _generate_single_file_with_model(
        self,
        prompt: str,
        plan: AgentPlan,
        path: str,
        existing_content: str | None,
        *,
        existed_before: bool,
    ) -> Generator[GenerationProgressEvent, None, GeneratedFile]:
        chunks: list[str] = []
        for chunk in self._iter_model_text(
            [
                {
                    "role": "system",
                    "content": (
                        "You generate exactly one file for a runnable starter project. "
                        "Return only the raw file content for the requested file path. "
                        "Do not wrap the response in markdown fences. "
                        "Keep imports, script tags, stylesheet references, and DOM hooks aligned with the planned file paths. "
                        "If the target file already exists, update it in place while preserving intent."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_single_file_prompt(
                        prompt,
                        plan,
                        path,
                        existing_content,
                    ),
                },
            ]
        ):
            if not chunk:
                continue
            chunks.append(chunk)
            yield GenerationProgressEvent(
                kind="chunk",
                path=path,
                existed_before=existed_before,
                used_model=True,
                content_chunk=chunk,
            )

        content = self._sanitize_generated_file_content(
            path,
            plan.planned_files,
            "".join(chunks).strip(),
        )
        if not content:
            raise ValueError("Model returned empty file content.")
        return GeneratedFile(
            path=path,
            content=content,
            existed_before=existed_before,
        )

    @staticmethod
    def _build_single_file_prompt(
        prompt: str,
        plan: AgentPlan,
        path: str,
        existing_content: str | None,
    ) -> str:
        existing_block = existing_content or "None"
        return (
            f"User request:\n{prompt}\n\n"
            f"Plan summary:\n{plan.summary}\n\n"
            f"Target file:\n{path}\n\n"
            f"Planned files:\n- " + "\n- ".join(plan.planned_files) + "\n\n"
            f"Implementation steps:\n- " + "\n- ".join(plan.implementation_steps) + "\n\n"
            f"Existing file contents:\n{existing_block}\n\n"
            "Generate the file content now."
        )

    def _get_model(self) -> ChatOpenAI:
        if self._model is None:
            self._model = ChatOpenAI(
                model=self.settings.model.model_name,
                api_key=self.settings.model.api_key,
                base_url=self.settings.model.ai_base_url,
                timeout=45.0,
                max_retries=1,
                temperature=0.2,
            )
        return self._model

    def _iter_model_text(self, messages: list[dict[str, str]]) -> Generator[str, None, None]:
        model = self._get_model()
        if hasattr(model, "stream"):
            for chunk in model.stream(messages):
                text = self._message_text(getattr(chunk, "content", ""))
                if text:
                    yield text
            return
        response = model.invoke(messages)
        text = self._message_text(response.content)
        if text:
            yield text

    def _model_is_configured(self) -> bool:
        key = self.settings.model.api_key.strip()
        base_url = self.settings.model.ai_base_url.strip()
        model_name = self.settings.model.model_name.strip()
        if not key or not base_url or not model_name:
            return False
        return not key.lower().startswith("your_")

    @classmethod
    def _message_text(cls, content: object) -> str:
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
            raise ValueError("Generation response did not contain JSON.")
        return stripped[start : end + 1]

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                stripped = "\n".join(lines[1:-1]).strip()
                if "\n" in stripped:
                    first_line, remainder = stripped.split("\n", 1)
                    if first_line.strip() in {
                        "html",
                        "css",
                        "javascript",
                        "js",
                        "json",
                        "markdown",
                        "md",
                    }:
                        stripped = remainder.strip()
        return stripped

    @classmethod
    def _sanitize_generated_file_content(
        cls,
        path: str,
        planned_files: list[str],
        text: str,
    ) -> str:
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        cleaned = cls._extract_target_file_block(path, planned_files, cleaned)
        cleaned = cls._strip_code_fences(cleaned)
        cleaned = cls._drop_leading_file_label(path, cleaned)
        cleaned = cls._trim_to_file_body(path, cleaned)
        cleaned = cls._remove_embedded_other_files(path, planned_files, cleaned)
        return cleaned.strip()

    @staticmethod
    def _extract_target_file_block(path: str, planned_files: list[str], text: str) -> str:
        lines = text.splitlines()
        if not lines:
            return text

        def labels_for(file_path: str) -> set[str]:
            normalized = file_path.replace("\\", "/").strip()
            base = Path(normalized).name
            return {
                normalized,
                base,
                f"`{normalized}`",
                f"`{base}`",
            }

        target_labels = labels_for(path)
        all_labels: dict[str, set[str]] = {
            item.replace("\\", "/").strip(): labels_for(item)
            for item in planned_files
        }
        start_index: int | None = None
        for index, line in enumerate(lines):
            if line.strip() in target_labels:
                start_index = index + 1
                break
        if start_index is None:
            return text

        end_index = len(lines)
        for index in range(start_index, len(lines)):
            current = lines[index].strip()
            for candidate_path, candidate_labels in all_labels.items():
                if candidate_path == path.replace("\\", "/").strip():
                    continue
                if current in candidate_labels:
                    end_index = index
                    break
            if end_index != len(lines):
                break
        return "\n".join(lines[start_index:end_index]).strip()

    @staticmethod
    def _drop_leading_file_label(path: str, text: str) -> str:
        normalized = path.replace("\\", "/").strip()
        base = Path(normalized).name
        labels = {
            normalized,
            base,
            f"`{normalized}`",
            f"`{base}`",
        }
        lines = text.splitlines()
        while lines and lines[0].strip() in labels:
            lines.pop(0)
        return "\n".join(lines).strip()

    @classmethod
    def _trim_to_file_body(cls, path: str, text: str) -> str:
        normalized = path.replace("\\", "/").lower()
        if normalized.endswith(".html"):
            return cls._trim_html(text)
        if normalized.endswith(".css"):
            return cls._trim_css(text)
        if normalized.endswith(".js"):
            return cls._trim_javascript(text)
        if normalized.endswith(".md"):
            return cls._trim_markdown(text)
        return text

    @staticmethod
    def _trim_html(text: str) -> str:
        lower = text.lower()
        start = lower.find("<!doctype html")
        if start == -1:
            start = lower.find("<html")
        if start == -1:
            return text
        end = lower.rfind("</html>")
        if end == -1:
            return text[start:].strip()
        return text[start : end + len("</html>")].strip()

    @staticmethod
    def _trim_css(text: str) -> str:
        lines = text.splitlines()
        content_start: int | None = None
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("@import", ":root", "/*")):
                content_start = index
                break
            if re.match(r"^(\*|html|body|main|section|header|footer|nav|button|a|img|svg|\.|#|\[).*(\{|,)$", stripped):
                content_start = index
                break
        if content_start is None:
            return text
        return "\n".join(lines[content_start:]).strip()

    @staticmethod
    def _trim_javascript(text: str) -> str:
        lines = text.splitlines()
        content_start: int | None = None
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("import ", "export ", "const ", "let ", "var ", "function ", "class ", "//", "/*", "document.", "window.", "(()")):
                content_start = index
                break
        if content_start is None:
            return text
        return "\n".join(lines[content_start:]).strip()

    @staticmethod
    def _trim_markdown(text: str) -> str:
        lines = text.splitlines()
        content_start: int | None = None
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "-", "1.", "2.", "3.")):
                content_start = index
                break
            if not re.match(r"^[A-Za-z0-9_/.-]+\.(html|css|js|md)$", stripped, flags=re.IGNORECASE):
                content_start = index
                break
        if content_start is None:
            return text
        return "\n".join(lines[content_start:]).strip()

    @staticmethod
    def _remove_embedded_other_files(path: str, planned_files: list[str], text: str) -> str:
        normalized = path.replace("\\", "/").lower()
        if not normalized.endswith(".md"):
            return text
        current_labels = {
            path.replace("\\", "/").lower(),
            Path(path).name.lower(),
        }
        other_labels = {
            label
            for item in planned_files
            for label in {item.replace("\\", "/").lower(), Path(item).name.lower()}
            if label not in current_labels
        }
        lines = text.splitlines()
        cutoff = len(lines)
        for index, line in enumerate(lines):
            lowered = line.strip().lower().strip("`")
            if not lowered:
                continue
            if any(
                re.search(rf"(^|[^a-z0-9_/.-]){re.escape(label)}($|[^a-z0-9_/.-])", lowered)
                for label in other_labels
            ):
                cutoff = index
                break
        return "\n".join(lines[:cutoff]).strip()

    @staticmethod
    def _load_existing_files(output_dir: Path, plan: AgentPlan) -> dict[str, str]:
        existing: dict[str, str] = {}
        for relative_path in plan.planned_files:
            target = output_dir / relative_path
            if target.exists() and target.is_file():
                existing[relative_path] = target.read_text(encoding="utf-8")
        return existing

    @classmethod
    def _infer_mode(cls, prompt: str, planned_files: list[str]) -> str:
        lowered = prompt.lower()
        joined_files = " ".join(path.lower() for path in planned_files)
        if any(
            token in lowered
            for token in {
                "static",
                "static page",
                "landing page",
                "showcase",
                "hero section",
                "illustration",
                "poster",
                "portrait",
                "anime girl",
                "pretty girl",
                "beautiful girl",
                "ui mock",
                "静态",
                "界面",
                "页面",
                "插画",
                "海报",
                "立绘",
                "美少女",
                "少女",
            }
        ):
            return "static_site"
        if any(
            token in lowered
            for token in {
                "flappy",
                "browser game",
                "web game",
                "arcade game",
                "canvas game",
                "platformer",
                "runner game",
                "小游戏",
                "网页游戏",
                "浏览器游戏",
                "街机游戏",
            }
        ):
            return "browser_game"
        if any(token in lowered for token in {"map", "trail", "hiking", "leaflet", "mapbox"}):
            return "map_site"
        if any(token in lowered for token in {"website", "web site", "landing page", "static site", "web app"}) or "index.html" in joined_files:
            return "static_site"
        return "generic"

    @staticmethod
    def _required_files(mode: str) -> list[str]:
        if mode == "browser_game":
            return ["index.html", "styles.css", "js/main.js", "js/game.js", "README.md"]
        if mode == "map_site":
            return ["index.html", "css/styles.css", "js/app.js", "README.md"]
        if mode == "static_site":
            return ["index.html", "styles.css", "js/app.js", "README.md"]
        return []

    @classmethod
    def _normalized_files(cls, mode: str, planned_files: list[str]) -> list[str]:
        files = [path.replace("\\", "/") for path in planned_files if path.strip()]
        required_files = cls._required_files(mode)
        if mode in {"browser_game", "static_site", "map_site"} and cls._has_web_scaffold(files):
            required_files = [path for path in required_files if path.lower().endswith("readme.md")]
        for required in required_files:
            if required not in files:
                files.append(required)
        deduped: list[str] = []
        for path in files:
            if path not in deduped:
                deduped.append(path)
        return deduped

    @staticmethod
    def _has_web_scaffold(planned_files: list[str]) -> bool:
        lowered = [path.lower() for path in planned_files]
        has_html = any(path.endswith(".html") for path in lowered)
        has_css = any(path.endswith(".css") for path in lowered)
        has_js = any(path.endswith(".js") for path in lowered)
        return has_html and has_css and has_js

    @staticmethod
    def _normalized_steps(mode: str, implementation_steps: list[str]) -> list[str]:
        steps = [step.strip() for step in implementation_steps if step.strip()]
        defaults: list[str] = []
        if mode == "browser_game":
            defaults = [
                "Build the game shell with a scoreboard, status text, and a canvas scene.",
                "Implement the core gameplay loop, player controls, obstacle or goal logic, and collision handling in JavaScript.",
                "Wire user input, restart behavior, and render updates so the game is playable immediately in the browser.",
                "Add styling and a short README explaining how to run the game locally.",
            ]
        elif mode == "static_site":
            defaults = [
                "Create the page structure and content sections in HTML.",
                "Add CSS for layout, spacing, and visual hierarchy.",
                "Implement JavaScript for page behavior and interactions.",
                "Document how to run and customize the generated site.",
            ]
        elif mode == "map_site":
            defaults = [
                "Create the responsive page shell and map container.",
                "Implement the map bootstrap and marker rendering logic.",
                "Add supporting UI content and trail cards around the map experience.",
                "Document how to run the generated site locally.",
            ]
        for step in defaults:
            if step not in steps:
                steps.append(step)
        return steps[:6]

    @staticmethod
    def _template_for_path(
        path: str,
        prompt: str,
        plan: AgentPlan,
        existing_content: str | None,
    ) -> str:
        normalized = path.replace("\\", "/").lower()
        is_leaflet = "leaflet" in prompt.lower()
        mode = ProjectGenerator._infer_mode(prompt, plan.planned_files)
        if existing_content is not None:
            return ProjectGenerator._update_existing_content(
                path=path,
                prompt=prompt,
                plan=plan,
                existing_content=existing_content,
            )

        if mode == "browser_game":
            game_template = ProjectGenerator._browser_game_template(normalized, prompt)
            if game_template is not None:
                return game_template

        if mode == "static_site" and mode != "map_site":
            static_template = ProjectGenerator._static_site_template(normalized, prompt, plan)
            if static_template is not None:
                return static_template

        if normalized.endswith("index.html"):
            map_css = (
                "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
                if is_leaflet
                else "https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.css"
            )
            map_js = (
                "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
                if is_leaflet
                else "https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.js"
            )
            entry_file = "js/app.js" if "js/app.js" in plan.planned_files else "js/map-init.js"
            return (
                "<!DOCTYPE html>\n"
                "<html lang=\"en\">\n"
                "<head>\n"
                "  <meta charset=\"UTF-8\" />\n"
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                "  <title>Trail Atlas</title>\n"
                f"  <link rel=\"stylesheet\" href=\"{map_css}\" />\n"
                "  <link rel=\"stylesheet\" href=\"css/styles.css\" />\n"
                "</head>\n"
                "<body>\n"
                "  <header class=\"hero\">\n"
                "    <p class=\"eyebrow\">DevMate Demo</p>\n"
                "    <h1>Find your next trail</h1>\n"
                "    <p class=\"lede\">A responsive map-first hiking website generated from the planning workflow.</p>\n"
                "  </header>\n"
                "  <main class=\"layout\">\n"
                "    <aside class=\"filters\">\n"
                "      <h2>Trail filters</h2>\n"
                "      <label><span>Difficulty</span><select><option>Any</option><option>Easy</option><option>Moderate</option><option>Hard</option></select></label>\n"
                "      <label><span>Length</span><select><option>Any</option><option>Under 5 km</option><option>5-10 km</option><option>10+ km</option></select></label>\n"
                "    </aside>\n"
                "    <section class=\"map-panel\">\n"
                "      <div id=\"map\" aria-label=\"Trail map\"></div>\n"
                "      <div id=\"trail-list\" class=\"trail-list\"></div>\n"
                "    </section>\n"
                "  </main>\n"
                f"  <script src=\"{map_js}\"></script>\n"
                f"  <script type=\"module\" src=\"{entry_file}\"></script>\n"
                "</body>\n"
                "</html>"
            )
        if normalized.endswith(".css"):
            return (
                ":root {\n"
                "  --sand: #f5efe6;\n"
                "  --forest: #1f4d3d;\n"
                "  --moss: #6f8f72;\n"
                "  --ink: #18231f;\n"
                "}\n\n"
                "* { box-sizing: border-box; }\n"
                "body { margin: 0; font-family: 'Segoe UI', sans-serif; color: var(--ink); background: linear-gradient(180deg, var(--sand), #ffffff); }\n"
                ".hero { padding: 2rem 1.5rem 1rem; }\n"
                ".eyebrow { text-transform: uppercase; letter-spacing: 0.12em; color: var(--moss); }\n"
                ".layout { display: grid; grid-template-columns: 320px 1fr; gap: 1rem; padding: 0 1.5rem 1.5rem; }\n"
                ".filters, .map-panel { background: rgba(255,255,255,0.86); border-radius: 20px; padding: 1rem; box-shadow: 0 18px 40px rgba(24,35,31,0.08); }\n"
                ".filters label { display: block; margin-bottom: 1rem; }\n"
                ".filters span { display: block; margin-bottom: 0.35rem; font-weight: 600; }\n"
                ".filters select { width: 100%; padding: 0.75rem; border-radius: 12px; border: 1px solid #d3ddd7; }\n"
                "#map { min-height: 420px; border-radius: 16px; }\n"
                ".trail-list { margin-top: 1rem; display: grid; gap: 0.75rem; }\n"
                ".trail-card { padding: 0.85rem 1rem; border-radius: 14px; background: #f8fbf9; border: 1px solid #e2ebe5; cursor: pointer; }\n"
                "@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } #map { min-height: 320px; } }\n"
            )
        if normalized.endswith("map-config.js") and is_leaflet:
            return (
                "export const defaultCenter = [39.9042, 116.4074];\n"
                "export const defaultZoom = 10;\n"
                "\n"
                "export function createBaseLayer(L) {\n"
                "  return L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {\n"
                "    attribution: '&copy; OpenStreetMap contributors',\n"
                "    maxZoom: 19,\n"
                "  });\n"
                "}\n"
            )
        if normalized.endswith("map-config.js"):
            return (
                "export const mapboxAccessToken = 'YOUR_MAPBOX_ACCESS_TOKEN';\n"
                "export const defaultCenter = [116.4074, 39.9042];\n"
                "export const defaultZoom = 10;\n"
                "export const mapStyle = 'mapbox://styles/mapbox/outdoors-v12';\n"
                "\n"
                "export const trailPoints = [\n"
                "  { name: 'Fragrant Hills Loop', distance: '6.2 km', difficulty: 'Moderate', coords: [116.188, 39.999] },\n"
                "  { name: 'Yangtai Mountain Ridge', distance: '9.4 km', difficulty: 'Hard', coords: [116.093, 40.071] },\n"
                "  { name: 'Olympic Forest Park Walk', distance: '4.1 km', difficulty: 'Easy', coords: [116.396, 40.024] },\n"
                "];\n"
            )
        if normalized.endswith("map-init.js"):
            return (
                "import { defaultCenter, defaultZoom, mapStyle, mapboxAccessToken, trailPoints } from './map-config.js';\n"
                "import { addTrailMarkers, renderTrailCards } from './markers.js';\n"
                "\n"
                "mapboxgl.accessToken = mapboxAccessToken;\n"
                "const map = new mapboxgl.Map({\n"
                "  container: 'map',\n"
                "  style: mapStyle,\n"
                "  center: defaultCenter,\n"
                "  zoom: defaultZoom,\n"
                "  cooperativeGestures: true,\n"
                "});\n"
                "\n"
                "window.addEventListener('resize', () => map.resize());\n"
                "const markers = addTrailMarkers(map, trailPoints);\n"
                "const list = document.getElementById('trail-list');\n"
                "renderTrailCards(trailPoints, list, (trail) => {\n"
                "  map.flyTo({ center: trail.coords, zoom: 12, essential: true });\n"
                "  const active = markers.find((item) => item.trail.name === trail.name);\n"
                "  if (active) {\n"
                "    active.marker.togglePopup();\n"
                "  }\n"
                "});\n"
            )
        if normalized.endswith("markers.js"):
            return (
                "export function renderTrailCards(trails, container, onSelect) {\n"
                "  container.innerHTML = '';\n"
                "  trails.forEach((trail) => {\n"
                "    const card = document.createElement('article');\n"
                "    card.className = 'trail-card';\n"
                "    card.innerHTML = `<h3>${trail.name}</h3><p>${trail.distance} - ${trail.difficulty}</p>`;\n"
                "    card.addEventListener('click', () => onSelect(trail));\n"
                "    container.appendChild(card);\n"
                "  });\n"
                "}\n"
                "\n"
                "export function addTrailMarkers(map, trails) {\n"
                "  return trails.map((trail) => {\n"
                "    const marker = new mapboxgl.Marker({ color: '#1f4d3d' })\n"
                "      .setLngLat(trail.coords)\n"
                "      .setPopup(new mapboxgl.Popup({ offset: 16 }).setHTML(`<strong>${trail.name}</strong><br />${trail.distance} - ${trail.difficulty}`))\n"
                "      .addTo(map);\n"
                "    return { trail, marker };\n"
                "  });\n"
                "}\n"
            )
        if normalized.endswith("map.js"):
            return (
                "const mapboxAccessToken = import.meta.env?.VITE_MAPBOX_ACCESS_TOKEN || 'YOUR_MAPBOX_ACCESS_TOKEN';\n"
                "mapboxgl.accessToken = mapboxAccessToken;\n"
                "\n"
                "export function createMap(containerId = 'map') {\n"
                "  return new mapboxgl.Map({\n"
                "    container: containerId,\n"
                "    style: 'mapbox://styles/mapbox/outdoors-v12',\n"
                "    center: [116.4074, 39.9042],\n"
                "    zoom: 10,\n"
                "    cooperativeGestures: true,\n"
                "  });\n"
                "}\n"
            )
        if normalized.endswith("geolocation.js"):
            return (
                "export function addGeolocationControl(map) {\n"
                "  const control = new mapboxgl.GeolocateControl({\n"
                "    positionOptions: { enableHighAccuracy: true },\n"
                "    trackUserLocation: true,\n"
                "    showUserHeading: true,\n"
                "  });\n"
                "  map.addControl(control, 'top-right');\n"
                "  return control;\n"
                "}\n"
            )
        if normalized.endswith("app.js") and is_leaflet:
            return (
                "import { createBaseLayer, defaultCenter, defaultZoom } from './map-config.js';\n"
                "\n"
                "const trails = [\n"
                "  { name: 'Fragrant Hills Loop', distance: '6.2 km', difficulty: 'Moderate', coords: [39.999, 116.188] },\n"
                "  { name: 'Yangtai Mountain Ridge', distance: '9.4 km', difficulty: 'Hard', coords: [40.071, 116.093] },\n"
                "  { name: 'Olympic Forest Park Walk', distance: '4.1 km', difficulty: 'Easy', coords: [40.024, 116.396] },\n"
                "];\n"
                "\n"
                "const map = L.map('map', { scrollWheelZoom: false }).setView(defaultCenter, defaultZoom);\n"
                "createBaseLayer(L).addTo(map);\n"
                "\n"
                "const list = document.getElementById('trail-list');\n"
                "trails.forEach((trail) => {\n"
                "  const marker = L.marker(trail.coords).addTo(map);\n"
                "  marker.bindPopup(`<strong>${trail.name}</strong><br />${trail.distance} - ${trail.difficulty}`);\n"
                "  const card = document.createElement('article');\n"
                "  card.className = 'trail-card';\n"
                "  card.innerHTML = `<h3>${trail.name}</h3><p>${trail.distance} - ${trail.difficulty}</p>`;\n"
                "  card.addEventListener('click', () => {\n"
                "    map.flyTo(trail.coords, 12, { duration: 0.8 });\n"
                "    marker.openPopup();\n"
                "  });\n"
                "  list.appendChild(card);\n"
                "});\n"
            )
        if normalized.endswith(".js"):
            return (
                f"// Generated starter for {path}\n"
                f"// Prompt: {prompt}\n"
                "export function bootstrap() {\n"
                "  return 'ready';\n"
                "}\n"
            )
        if normalized.endswith("readme.md"):
            return (
                "# Generated Project\n\n"
                f"Prompt: {prompt}\n\n"
                "## Files\n\n"
                + "\n".join(f"- `{item}`" for item in plan.planned_files)
                + "\n\n## Next Steps\n\n"
                + "\n".join(f"{idx}. {step}" for idx, step in enumerate(plan.implementation_steps, start=1))
            )
        if normalized.endswith(".py"):
            return (
                f'"""Generated starter for {path}."""\n\n'
                "from __future__ import annotations\n\n\n"
                "def main() -> None:\n"
                "    \"\"\"Entry point placeholder.\"\"\"\n"
                "    return None\n"
            )
        if normalized.endswith(".env.example"):
            return "MAPBOX_ACCESS_TOKEN=your_mapbox_access_token_here\n"
        if normalized.endswith(".md"):
            return (
                f"# {Path(path).stem.replace('-', ' ').title()}\n\n"
                f"Generated from prompt: {prompt}\n"
            )
        return f"Generated placeholder for {path}\n"

    @staticmethod
    def _browser_game_template(normalized: str, prompt: str) -> str | None:
        is_flappy = "flappy" in prompt.lower()
        if normalized.endswith("index.html"):
            return (
                "<!DOCTYPE html>\n"
                "<html lang=\"en\">\n"
                "<head>\n"
                "  <meta charset=\"UTF-8\" />\n"
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                f"  <title>{'Flappy Bird Clone' if is_flappy else 'Browser Game Demo'}</title>\n"
                "  <link rel=\"stylesheet\" href=\"styles.css\" />\n"
                "</head>\n"
                "<body>\n"
                "  <main class=\"game-shell\">\n"
                "    <section class=\"hero\">\n"
                "      <p class=\"eyebrow\">DevMate Browser Game</p>\n"
                f"      <h1>{'Flappy Bird Clone' if is_flappy else 'Browser Game Demo'}</h1>\n"
                f"      <p class=\"lede\">Generated from prompt: {prompt}</p>\n"
                "    </section>\n"
                "    <section class=\"game-layout\">\n"
                "      <div class=\"hud\">\n"
                "        <div><span>Score</span><strong id=\"score\">0</strong></div>\n"
                "        <div><span>Best</span><strong id=\"best-score\">0</strong></div>\n"
                "        <button id=\"start-button\" type=\"button\">Start / Restart</button>\n"
                "      </div>\n"
                f"      <canvas id=\"game-canvas\" width=\"420\" height=\"640\" aria-label=\"{'Flappy Bird game canvas' if is_flappy else 'Browser game canvas'}\"></canvas>\n"
                f"      <p id=\"status\" class=\"status\">{'Press Start or hit Space to flap.' if is_flappy else 'Press Start to begin playing.'}</p>\n"
                "    </section>\n"
                "  </main>\n"
                "  <script type=\"module\" src=\"js/main.js\"></script>\n"
                "</body>\n"
                "</html>"
            )
        if normalized.endswith("styles.css"):
            return (
                ":root {\n"
                "  --sky: #d8f0ff;\n"
                "  --sky-deep: #9dd8ff;\n"
                "  --ground: #f0d082;\n"
                "  --ink: #142338;\n"
                "  --panel: rgba(255, 255, 255, 0.82);\n"
                "  --accent: #ff7a18;\n"
                "}\n\n"
                "* { box-sizing: border-box; }\n"
                "body { margin: 0; min-height: 100vh; font-family: 'Segoe UI', sans-serif; color: var(--ink); background: linear-gradient(180deg, var(--sky), var(--sky-deep)); }\n"
                ".game-shell { max-width: 980px; margin: 0 auto; padding: 2rem 1rem 3rem; }\n"
                ".hero { margin-bottom: 1.5rem; }\n"
                ".eyebrow { margin: 0 0 0.5rem; text-transform: uppercase; letter-spacing: 0.18em; font-size: 0.82rem; color: #0d5d86; }\n"
                ".hero h1 { margin: 0; font-size: clamp(2rem, 5vw, 3.8rem); }\n"
                ".lede { max-width: 44rem; color: rgba(20, 35, 56, 0.8); }\n"
                ".game-layout { display: grid; gap: 1rem; }\n"
                ".hud { display: flex; flex-wrap: wrap; align-items: center; gap: 1rem; padding: 1rem 1.2rem; border-radius: 20px; background: var(--panel); box-shadow: 0 18px 40px rgba(20, 35, 56, 0.12); }\n"
                ".hud div { display: grid; gap: 0.15rem; min-width: 90px; }\n"
                ".hud span { font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.12em; color: rgba(20, 35, 56, 0.6); }\n"
                ".hud strong { font-size: 1.6rem; }\n"
                ".hud button { margin-left: auto; border: 0; border-radius: 999px; padding: 0.85rem 1.25rem; font-weight: 700; background: var(--accent); color: white; cursor: pointer; }\n"
                "#game-canvas { width: min(100%, 420px); justify-self: center; border-radius: 28px; background: linear-gradient(180deg, #7fd2ff, #c5f4ff 75%); box-shadow: 0 20px 50px rgba(20, 35, 56, 0.18); }\n"
                ".status { margin: 0; text-align: center; font-weight: 600; }\n"
            )
        if normalized.endswith("js/main.js"):
            return (
                f"import {{ {'mountFlappyBird' if is_flappy else 'mountBrowserGame'} }} from './game.js';\n\n"
                "const canvas = document.getElementById('game-canvas');\n"
                "const score = document.getElementById('score');\n"
                "const bestScore = document.getElementById('best-score');\n"
                "const status = document.getElementById('status');\n"
                "const startButton = document.getElementById('start-button');\n\n"
                "if (!(canvas instanceof HTMLCanvasElement) || !score || !bestScore || !status || !(startButton instanceof HTMLButtonElement)) {\n"
                "  throw new Error('Game UI failed to initialize.');\n"
                "}\n\n"
                f"{'mountFlappyBird' if is_flappy else 'mountBrowserGame'}({{ canvas, scoreEl: score, bestEl: bestScore, statusEl: status, startButton }});\n"
            )
        if normalized.endswith("js/game.js"):
            if not is_flappy:
                return (
                    "function randomBetween(min, max) {\n"
                    "  return Math.random() * (max - min) + min;\n"
                    "}\n\n"
                    "export function mountBrowserGame({ canvas, scoreEl, bestEl, statusEl, startButton }) {\n"
                    "  const ctx = canvas.getContext('2d');\n"
                    "  if (!ctx) throw new Error('Canvas 2D context unavailable.');\n"
                    "  const player = { x: 72, y: canvas.height / 2, size: 24, velocityY: 0 };\n"
                    "  let stars = [];\n"
                    "  let running = false;\n"
                    "  let score = 0;\n"
                    "  let best = Number(localStorage.getItem('devmate-browser-game-best') || '0');\n"
                    "  let animationFrame = 0;\n"
                    "  let lastTime = 0;\n"
                    "  let spawnTimer = 0;\n\n"
                    "  function reset() {\n"
                    "    player.y = canvas.height / 2;\n"
                    "    player.velocityY = 0;\n"
                    "    stars = [];\n"
                    "    score = 0;\n"
                    "    spawnTimer = 0;\n"
                    "    scoreEl.textContent = '0';\n"
                    "    bestEl.textContent = String(best);\n"
                    "    statusEl.textContent = 'Collect glowing stars and avoid falling off the stage.';\n"
                    "  }\n\n"
                    "  function spawnStar() {\n"
                    "    stars.push({ x: canvas.width + 30, y: randomBetween(60, canvas.height - 80), size: randomBetween(12, 18), claimed: false });\n"
                    "  }\n\n"
                    "  function jump() {\n"
                    "    if (!running) {\n"
                    "      start();\n"
                    "      return;\n"
                    "    }\n"
                    "    player.velocityY = -320;\n"
                    "  }\n\n"
                    "  function update(delta) {\n"
                    "    player.velocityY += 900 * delta;\n"
                    "    player.y += player.velocityY * delta;\n"
                    "    spawnTimer += delta;\n"
                    "    if (spawnTimer >= 1.1) { spawnTimer = 0; spawnStar(); }\n"
                    "    stars = stars.map((star) => ({ ...star, x: star.x - 180 * delta })).filter((star) => star.x > -40);\n"
                    "    for (const star of stars) {\n"
                    "      if (!star.claimed && Math.abs(star.x - player.x) < star.size + player.size / 2 && Math.abs(star.y - player.y) < star.size + player.size / 2) {\n"
                    "        star.claimed = true;\n"
                    "        score += 1;\n"
                    "        scoreEl.textContent = String(score);\n"
                    "      }\n"
                    "    }\n"
                    "    if (player.y < 0 || player.y > canvas.height) {\n"
                    "      gameOver();\n"
                    "    }\n"
                    "  }\n\n"
                    "  function draw() {\n"
                    "    const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);\n"
                    "    gradient.addColorStop(0, '#111827');\n"
                    "    gradient.addColorStop(1, '#312e81');\n"
                    "    ctx.fillStyle = gradient;\n"
                    "    ctx.fillRect(0, 0, canvas.width, canvas.height);\n"
                    "    stars.forEach((star) => {\n"
                    "      if (star.claimed) return;\n"
                    "      ctx.fillStyle = '#facc15';\n"
                    "      ctx.beginPath();\n"
                    "      ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);\n"
                    "      ctx.fill();\n"
                    "    });\n"
                    "    ctx.fillStyle = '#f9a8d4';\n"
                    "    ctx.beginPath();\n"
                    "    ctx.roundRect(player.x - 20, player.y - 28, 40, 56, 18);\n"
                    "    ctx.fill();\n"
                    "    ctx.fillStyle = '#ffffff';\n"
                    "    ctx.beginPath();\n"
                    "    ctx.arc(player.x + 8, player.y - 8, 4, 0, Math.PI * 2);\n"
                    "    ctx.fill();\n"
                    "  }\n\n"
                    "  function frame(time) {\n"
                    "    if (!running) return;\n"
                    "    if (!lastTime) lastTime = time;\n"
                    "    const delta = Math.min((time - lastTime) / 1000, 0.032);\n"
                    "    lastTime = time;\n"
                    "    update(delta);\n"
                    "    draw();\n"
                    "    animationFrame = window.requestAnimationFrame(frame);\n"
                    "  }\n\n"
                    "  function start() {\n"
                    "    window.cancelAnimationFrame(animationFrame);\n"
                    "    lastTime = 0;\n"
                    "    running = true;\n"
                    "    reset();\n"
                    "    animationFrame = window.requestAnimationFrame(frame);\n"
                    "  }\n\n"
                    "  function gameOver() {\n"
                    "    if (!running) return;\n"
                    "    running = false;\n"
                    "    window.cancelAnimationFrame(animationFrame);\n"
                    "    best = Math.max(best, score);\n"
                    "    localStorage.setItem('devmate-browser-game-best', String(best));\n"
                    "    bestEl.textContent = String(best);\n"
                    "    statusEl.textContent = `Game over. You collected ${score} stars.`;\n"
                    "    draw();\n"
                    "  }\n\n"
                    "  startButton.addEventListener('click', start);\n"
                    "  window.addEventListener('keydown', (event) => { if (event.code === 'Space') { event.preventDefault(); jump(); } });\n"
                    "  canvas.addEventListener('pointerdown', jump);\n"
                    "  bestEl.textContent = String(best);\n"
                    "  draw();\n"
                    "}\n"
                )
            return (
                "const PIPE_WIDTH = 72;\n"
                "const PIPE_GAP = 160;\n"
                "const PIPE_SPEED = 160;\n"
                "const GRAVITY = 1400;\n"
                "const FLAP_VELOCITY = -420;\n"
                "const PIPE_INTERVAL = 1.35;\n\n"
                "function randomBetween(min, max) {\n"
                "  return Math.random() * (max - min) + min;\n"
                "}\n\n"
                "export function mountFlappyBird({ canvas, scoreEl, bestEl, statusEl, startButton }) {\n"
                "  const ctx = canvas.getContext('2d');\n"
                "  if (!ctx) throw new Error('Canvas 2D context unavailable.');\n"
                "  let animationFrame = 0;\n"
                "  let lastTime = 0;\n"
                "  let accumulator = 0;\n"
                "  let running = false;\n"
                "  let score = 0;\n"
                "  let best = Number(localStorage.getItem('devmate-flappy-best') || '0');\n"
                "  let bird = { x: 110, y: canvas.height / 2, velocityY: 0, radius: 18, rotation: 0 };\n"
                "  let pipes = [];\n"
                "  function reset() { score = 0; accumulator = 0; bird = { x: 110, y: canvas.height / 2, velocityY: 0, radius: 18, rotation: 0 }; pipes = []; scoreEl.textContent = '0'; bestEl.textContent = String(best); statusEl.textContent = 'Tap Space, click, or touch to keep flying.'; }\n"
                "  function spawnPipe() { const gapTop = randomBetween(120, canvas.height - 220); pipes.push({ x: canvas.width + PIPE_WIDTH, gapTop, passed: false }); }\n"
                "  function flap() { if (!running) { start(); return; } bird.velocityY = FLAP_VELOCITY; }\n"
                "  function collide(pipe) { const withinX = bird.x + bird.radius > pipe.x && bird.x - bird.radius < pipe.x + PIPE_WIDTH; const hitsTop = bird.y - bird.radius < pipe.gapTop; const hitsBottom = bird.y + bird.radius > pipe.gapTop + PIPE_GAP; return withinX && (hitsTop || hitsBottom); }\n"
                "  function update(delta) { bird.velocityY += GRAVITY * delta; bird.y += bird.velocityY * delta; bird.rotation = Math.max(-0.6, Math.min(1.2, bird.velocityY / 500)); accumulator += delta; if (accumulator >= PIPE_INTERVAL) { accumulator = 0; spawnPipe(); } pipes = pipes.map((pipe) => ({ ...pipe, x: pipe.x - PIPE_SPEED * delta })).filter((pipe) => pipe.x + PIPE_WIDTH > -20); for (const pipe of pipes) { if (!pipe.passed && pipe.x + PIPE_WIDTH < bird.x) { pipe.passed = true; score += 1; scoreEl.textContent = String(score); } if (collide(pipe)) { gameOver(); } } if (bird.y + bird.radius >= canvas.height - 40 || bird.y - bird.radius <= 0) { gameOver(); } }\n"
                "  function draw() { const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height); gradient.addColorStop(0, '#7fd2ff'); gradient.addColorStop(1, '#d7f6ff'); ctx.fillStyle = gradient; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = '#e7c77a'; ctx.fillRect(0, canvas.height - 40, canvas.width, 40); ctx.fillStyle = '#2f9954'; pipes.forEach((pipe) => { ctx.fillRect(pipe.x, 0, PIPE_WIDTH, pipe.gapTop); ctx.fillRect(pipe.x, pipe.gapTop + PIPE_GAP, PIPE_WIDTH, canvas.height - pipe.gapTop - PIPE_GAP); }); ctx.save(); ctx.translate(bird.x, bird.y); ctx.rotate(bird.rotation); ctx.fillStyle = '#ffb11b'; ctx.beginPath(); ctx.arc(0, 0, bird.radius, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = '#142338'; ctx.beginPath(); ctx.arc(7, -5, 3.5, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = '#ff7a18'; ctx.beginPath(); ctx.moveTo(14, 2); ctx.lineTo(28, 0); ctx.lineTo(14, -4); ctx.closePath(); ctx.fill(); ctx.restore(); }\n"
                "  function frame(time) { if (!running) return; if (!lastTime) lastTime = time; const delta = Math.min((time - lastTime) / 1000, 0.032); lastTime = time; update(delta); draw(); animationFrame = window.requestAnimationFrame(frame); }\n"
                "  function start() { window.cancelAnimationFrame(animationFrame); lastTime = 0; running = true; reset(); spawnPipe(); bird.velocityY = FLAP_VELOCITY; animationFrame = window.requestAnimationFrame(frame); }\n"
                "  function gameOver() { if (!running) return; running = false; window.cancelAnimationFrame(animationFrame); best = Math.max(best, score); localStorage.setItem('devmate-flappy-best', String(best)); bestEl.textContent = String(best); statusEl.textContent = `Game over. Final score: ${score}. Press Start or Space to play again.`; draw(); }\n"
                "  startButton.addEventListener('click', start);\n"
                "  window.addEventListener('keydown', (event) => { if (event.code === 'Space') { event.preventDefault(); flap(); } });\n"
                "  canvas.addEventListener('pointerdown', flap);\n"
                "  bestEl.textContent = String(best);\n"
                "  draw();\n"
                "}\n"
            )
        if normalized.endswith("readme.md"):
            if not is_flappy:
                return (
                    "# Browser Game Demo\n\n"
                    "A small browser game scaffold generated by DevMate.\n\n"
                    "## Run\n\n"
                    "1. Open `index.html` in a browser, or serve the folder with a static file server.\n"
                    "2. Click **Start / Restart** or press the space bar to begin.\n"
                    "3. Collect the glowing stars and try to beat your best score.\n"
                )
            return (
                "# Flappy Bird Web Game\n\n"
                "A small browser game scaffold generated by DevMate.\n\n"
                "## Run\n\n"
                "1. Open `index.html` in a browser, or serve the folder with a static file server.\n"
                "2. Click **Start / Restart** or press the space bar to flap.\n"
                "3. Avoid the pipes and keep increasing your score.\n"
            )
        return None

    @staticmethod
    def _static_site_template(normalized: str, prompt: str, plan: AgentPlan) -> str | None:
        css_path = next((item for item in plan.planned_files if item.lower().endswith(".css")), "styles.css")
        js_path = next((item for item in plan.planned_files if item.lower().endswith(".js")), "js/app.js")
        if normalized.endswith("index.html"):
            return (
                "<!DOCTYPE html>\n"
                "<html lang=\"en\">\n"
                "<head>\n"
                "  <meta charset=\"UTF-8\" />\n"
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                "  <title>DevMate Site</title>\n"
                f"  <link rel=\"stylesheet\" href=\"{css_path}\" />\n"
                "</head>\n"
                "<body>\n"
                "  <main class=\"shell\">\n"
                "    <section class=\"hero\">\n"
                "      <p class=\"eyebrow\">Generated by DevMate</p>\n"
                "      <h1>Static Web Experience</h1>\n"
                f"      <p>{prompt}</p>\n"
                "      <button id=\"cta\" type=\"button\">Explore</button>\n"
                "    </section>\n"
                "    <section class=\"grid\" id=\"feature-grid\"></section>\n"
                "  </main>\n"
                f"  <script type=\"module\" src=\"{js_path}\"></script>\n"
                "</body>\n"
                "</html>"
            )
        if normalized.endswith("styles.css"):
            return (
                "body { margin: 0; min-height: 100vh; font-family: 'Segoe UI', sans-serif; background: linear-gradient(180deg, #f7fafc, #ffffff); color: #0f172a; }\n"
                ".shell { max-width: 1100px; margin: 0 auto; padding: 2rem 1rem 3rem; }\n"
                ".hero { padding: 2rem; border-radius: 24px; background: radial-gradient(circle at top left, rgba(59,130,246,0.14), transparent 35%), white; box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08); }\n"
                ".eyebrow { text-transform: uppercase; letter-spacing: 0.15em; color: #3b82f6; }\n"
                ".grid { display: grid; gap: 1rem; margin-top: 1.25rem; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }\n"
                ".card { border-radius: 18px; padding: 1.2rem; background: white; border: 1px solid #dbe4ef; }\n"
                "button { border: 0; border-radius: 999px; padding: 0.8rem 1.15rem; background: #3b82f6; color: white; font-weight: 700; cursor: pointer; }\n"
            )
        if normalized.endswith("js/app.js"):
            return (
                "const features = [\n"
                "  { title: 'Intentional layout', description: 'A clear content hierarchy and reusable sections.' },\n"
                "  { title: 'Interactive behavior', description: 'A starter button interaction and dynamic content render.' },\n"
                "  { title: 'Fast iteration', description: 'Simple files that are easy to extend after generation.' },\n"
                "];\n\n"
                "const grid = document.getElementById('feature-grid');\n"
                "const cta = document.getElementById('cta');\n"
                "if (grid) {\n"
                "  features.forEach((feature) => {\n"
                "    const card = document.createElement('article');\n"
                "    card.className = 'card';\n"
                "    card.innerHTML = `<h2>${feature.title}</h2><p>${feature.description}</p>`;\n"
                "    grid.appendChild(card);\n"
                "  });\n"
                "}\n"
                "cta?.addEventListener('click', () => {\n"
                "  cta.textContent = 'Ready to build';\n"
                "});\n"
            )
        if normalized.endswith("readme.md"):
            return (
                "# Static Site\n\n"
                "Open `index.html` directly in a browser, or serve the folder with a small static server.\n"
            )
        return None
    @staticmethod
    def _update_existing_content(
        *,
        path: str,
        prompt: str,
        plan: AgentPlan,
        existing_content: str,
    ) -> str:
        normalized = path.replace("\\", "/").lower()
        marker = "Generated from prompt:"

        if normalized.endswith(".md"):
            lines = [
                existing_content.rstrip(),
                "",
                "## DevMate Update",
                "",
                f"Generated from prompt: {prompt}",
                "",
                "### Planned Next Steps",
                "",
            ]
            lines.extend(
                f"{index}. {step}" for index, step in enumerate(plan.implementation_steps, start=1)
            )
            return "\n".join(lines).strip() + "\n"

        if marker in existing_content:
            return existing_content

        comment_prefix = "//"
        if normalized.endswith(".html"):
            comment_prefix = "<!--"
            comment_suffix = " -->"
            update_line = f"{comment_prefix} Generated from prompt: {prompt}{comment_suffix}"
        elif normalized.endswith(".css"):
            comment_prefix = "/*"
            comment_suffix = " */"
            update_line = f"{comment_prefix} Generated from prompt: {prompt}{comment_suffix}"
        else:
            update_line = f"{comment_prefix} Generated from prompt: {prompt}"

        return existing_content.rstrip() + "\n\n" + update_line + "\n"


