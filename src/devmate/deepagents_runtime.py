"""Deepagents-based runtime skeleton for direct codebase editing."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse
from deepagents.middleware.skills import SkillMetadata, _list_skills
from langchain_openai import ChatOpenAI
from langsmith.run_helpers import traceable

from devmate.agent_runtime import PromptResult
from devmate.config_loader import AppSettings
from devmate.mcp_client import SearchMcpClient, SearchResult
from devmate.rag_pipeline import KnowledgeBasePipeline, KnowledgeSnippet
from devmate.session_store import SessionStore, SessionTurn
from devmate.skill_registry import SkillNote, SkillRegistry


@dataclass
class _TrackedState:
    retrieved_sources: list[str]
    local_snippets: list[KnowledgeSnippet]
    matched_skills: list[str]
    web_results: list[SearchResult]
    web_search_attempted: bool
    web_search_error: str | None


class DevMateLocalShellBackend(LocalShellBackend):
    """Local backend with UTF-8 tolerant command execution for Windows hosts."""

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        if not command or not isinstance(command, str):
            return ExecuteResponse(
                output="Error: Command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )

        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            msg = f"timeout must be positive, got {effective_timeout}"
            raise ValueError(msg)

        try:
            result = subprocess.run(
                command,
                check=False,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                env=self._env,
                cwd=str(self.cwd),
            )
            output_parts: list[str] = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                stderr_lines = result.stderr.strip().split("\n")
                output_parts.extend(f"[stderr] {line}" for line in stderr_lines)

            output = "\n".join(output_parts) if output_parts else "<no output>"
            truncated = False
            if len(output) > self._max_output_bytes:
                output = output[: self._max_output_bytes]
                output += f"\n\n... Output truncated at {self._max_output_bytes} bytes."
                truncated = True
            if result.returncode != 0:
                output = f"{output.rstrip()}\n\nExit code: {result.returncode}"
            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Error: Command timed out after {effective_timeout} seconds.",
                exit_code=124,
                truncated=False,
            )
        except Exception as exc:  # noqa: BLE001
            return ExecuteResponse(
                output=f"Error executing command ({type(exc).__name__}): {exc}",
                exit_code=1,
                truncated=False,
            )


class DeepAgentsRuntime:
    """Runtime wrapper that routes execution through deepagents."""

    def __init__(
        self,
        settings: AppSettings,
        search_client: SearchMcpClient | None = None,
        session_store: SessionStore | None = None,
        skill_registry: SkillRegistry | None = None,
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
        self.session_store = session_store or SessionStore(Path(".sessions"))
        self.skill_registry = skill_registry or SkillRegistry(Path(settings.skills.skills_dir))

    @traceable(run_type="chain", name="deepagents_handle_prompt")
    def handle_prompt(
        self,
        prompt: str,
        *,
        save_skill_name: str | None = None,
        generate_output_dir: Path | None = None,
        session_id: str | None = None,
    ) -> PromptResult:
        target_root = (
            generate_output_dir.resolve()
            if generate_output_dir is not None
            else Path.cwd().resolve()
        )
        target_root.mkdir(parents=True, exist_ok=True)
        workspace_root = self._workspace_root(target_root)
        before = self._snapshot_files(target_root)
        tracked = _TrackedState([], [], [], [], False, None)
        saved_skill_path: str | None = None

        try:
            agent = self._build_agent(
                prompt=prompt,
                workspace_root=workspace_root,
                target_root=target_root,
                target_root_virtual=self._virtual_target_path(workspace_root, target_root),
                tracked=tracked,
            )
            result = agent.invoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": self._compose_user_prompt(
                                prompt,
                                workspace_root=workspace_root,
                                target_root=target_root,
                                target_root_virtual=self._virtual_target_path(workspace_root, target_root),
                            ),
                        }
                    ]
                }
            )
            assistant_text = self._extract_assistant_text(result)
            after = self._snapshot_files(target_root)
            created_files, modified_files, deleted_files = self._diff_files(before, after)
            generated_files = [*created_files, *modified_files, *deleted_files]
            summary = self._summarize_result(prompt, assistant_text, generated_files)
            steps = self._extract_steps(assistant_text, generated_files)

            if save_skill_name:
                note = self._build_skill_note(save_skill_name, prompt, summary, steps)
                saved_skill_path = str(self.skill_registry.save(note))

            response = PromptResult(
                session_id=session_id,
                summary=summary,
                planned_files=generated_files or self._planned_files_from_text(assistant_text),
                implementation_steps=steps,
                retrieved_sources=tracked.retrieved_sources,
                matched_skills=tracked.matched_skills,
                web_results=tracked.web_results,
                web_search_attempted=tracked.web_search_attempted,
                agent_used_model=self._model_is_configured(),
                generation_output_dir=str(target_root) if generate_output_dir is not None else None,
                generated_files=generated_files or None,
                generated_created_files=created_files or None,
                generated_modified_files=modified_files or None,
                generated_deleted_files=deleted_files or None,
                generation_used_model=bool(generated_files),
                saved_skill_path=saved_skill_path,
                web_search_error=tracked.web_search_error,
            )
            self._persist_turn(session_id, prompt, response)
            return response
        except Exception as exc:
            response = PromptResult(
                session_id=session_id,
                summary="Deepagents runtime failed before completing the task.",
                planned_files=[],
                implementation_steps=[
                    "Inspect the runtime error and retry with a narrower prompt."
                ],
                retrieved_sources=tracked.retrieved_sources,
                matched_skills=tracked.matched_skills,
                web_results=tracked.web_results,
                web_search_attempted=tracked.web_search_attempted,
                agent_used_model=self._model_is_configured(),
                generation_output_dir=str(target_root) if generate_output_dir is not None else None,
                generation_used_model=False,
                saved_skill_path=saved_skill_path,
                web_search_error=tracked.web_search_error,
                agent_error=str(exc),
            )
            self._persist_turn(session_id, prompt, response)
            return response

    def stream_prompt(
        self,
        prompt: str,
        *,
        save_skill_name: str | None = None,
        generate_output_dir: Path | None = None,
        session_id: str,
    ) -> Iterator[dict[str, object]]:
        target_root = (
            generate_output_dir.resolve()
            if generate_output_dir is not None
            else Path.cwd().resolve()
        )
        target_root.mkdir(parents=True, exist_ok=True)
        workspace_root = self._workspace_root(target_root)
        before = self._snapshot_files(target_root)
        tracked = _TrackedState([], [], [], [], False, None)
        saved_skill_path: str | None = None
        assistant_text = ""

        yield {
            "type": "planning",
            "step": {
                "id": "deepagents-runtime",
                "title": "Run deepagents runtime",
                "description": "Delegating execution to deepagents with filesystem tools.",
                "status": "running",
            },
        }
        try:
            agent = self._build_agent(
                prompt=prompt,
                workspace_root=workspace_root,
                target_root=target_root,
                target_root_virtual=self._virtual_target_path(workspace_root, target_root),
                tracked=tracked,
            )
            if tracked.matched_skills:
                yield {
                    "type": "search",
                    "results": [
                        {
                            "id": f"skill-{index}",
                            "title": name,
                            "content": "Loaded from deepagents skills middleware.",
                            "source": "skill",
                            "score": 0.75,
                        }
                        for index, name in enumerate(tracked.matched_skills)
                    ],
                }
            tool_call_args: dict[str, dict[str, object]] = {}

            for update in agent.stream(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": self._compose_user_prompt(
                                prompt,
                                workspace_root=workspace_root,
                                target_root=target_root,
                                target_root_virtual=self._virtual_target_path(workspace_root, target_root),
                            ),
                        }
                    ]
                },
                stream_mode="updates",
            ):
                yield from self._updates_to_events(
                    update,
                    tracked=tracked,
                    tool_call_args=tool_call_args,
                    before_snapshot=before,
                )
                assistant_text = self._extract_assistant_text(update) or assistant_text

            after = self._snapshot_files(target_root)
            created_files, modified_files, deleted_files = self._diff_files(before, after)
            generated_files = [*created_files, *modified_files, *deleted_files]
            summary = self._summarize_result(prompt, assistant_text, generated_files)
            steps = self._extract_steps(assistant_text, generated_files)

            if save_skill_name:
                note = self._build_skill_note(save_skill_name, prompt, summary, steps)
                saved_skill_path = str(self.skill_registry.save(note))

            result = PromptResult(
                session_id=session_id,
                summary=summary,
                planned_files=generated_files or self._planned_files_from_text(assistant_text),
                implementation_steps=steps,
                retrieved_sources=tracked.retrieved_sources,
                matched_skills=tracked.matched_skills,
                web_results=tracked.web_results,
                web_search_attempted=tracked.web_search_attempted,
                agent_used_model=self._model_is_configured(),
                generation_output_dir=str(target_root) if generate_output_dir is not None else None,
                generated_files=generated_files or None,
                generated_created_files=created_files or None,
                generated_modified_files=modified_files or None,
                generated_deleted_files=deleted_files or None,
                generation_used_model=bool(generated_files),
                saved_skill_path=saved_skill_path,
                web_search_error=tracked.web_search_error,
            )
            self._persist_turn(session_id, prompt, result)
            yield {
                "type": "planning",
                "step": {
                    "id": "deepagents-runtime",
                    "title": "Run deepagents runtime",
                    "description": "Delegating execution to deepagents with filesystem tools.",
                    "status": "completed",
                    "output": result.summary,
                },
            }
            for chunk in self._chunk_content(self._render_assistant_message(result)):
                yield {"type": "content", "content": chunk}
            yield {"type": "complete", "summary": result.summary}
        except Exception as exc:
            result = PromptResult(
                session_id=session_id,
                summary="Deepagents runtime failed before completing the task.",
                planned_files=[],
                implementation_steps=[
                    "Inspect the runtime error and retry with a narrower prompt."
                ],
                retrieved_sources=tracked.retrieved_sources,
                matched_skills=tracked.matched_skills,
                web_results=tracked.web_results,
                web_search_attempted=tracked.web_search_attempted,
                agent_used_model=self._model_is_configured(),
                generation_output_dir=str(target_root) if generate_output_dir is not None else None,
                generation_used_model=False,
                saved_skill_path=saved_skill_path,
                web_search_error=tracked.web_search_error,
                agent_error=str(exc),
            )
            self._persist_turn(session_id, prompt, result)
            yield {
                "type": "planning",
                "step": {
                    "id": "deepagents-runtime",
                    "title": "Run deepagents runtime",
                    "description": "Delegating execution to deepagents with filesystem tools.",
                    "status": "failed",
                    "output": str(exc),
                },
            }
            yield {"type": "error", "message": str(exc)}

    def _build_agent(
        self,
        *,
        prompt: str,
        workspace_root: Path,
        target_root: Path,
        target_root_virtual: str,
        tracked: _TrackedState,
    ):
        backend = DevMateLocalShellBackend(
            root_dir=workspace_root,
            virtual_mode=True,
            timeout=120,
            inherit_env=False,
            env={},
        )
        skill_sources = self._skills_sources(workspace_root)
        skill_candidates = self._rank_skill_candidates(
            self._load_deepagents_skills(backend, skill_sources),
            prompt,
        )
        tracked.matched_skills = [item["name"] for item in skill_candidates]

        def delete_file(file_path: str) -> str:
            """Delete a file inside the active workspace."""

            normalized = file_path.lstrip("/").strip()
            if not normalized:
                return "Delete failed: empty file path."
            target = (workspace_root / normalized).resolve()
            try:
                target.relative_to(workspace_root.resolve())
            except ValueError:
                return f"Delete failed: {file_path} is outside the workspace."
            if not target.exists():
                return f"Delete skipped: {normalized} does not exist."
            if not target.is_file():
                return f"Delete failed: {normalized} is not a file."
            target.unlink()
            return f"Deleted file /{normalized}"

        def run_command(command: str) -> str:
            """Run a workspace-scoped command when the task requires validation or execution."""

            normalized = command.strip()
            if not normalized:
                return "Command execution failed: empty command."
            response = backend.execute(normalized, timeout=60)
            output = response.output.strip()
            if not output:
                output = "(no output)"
            suffix = " [truncated]" if response.truncated else ""
            return f"exit_code={response.exit_code}{suffix}\n{output}"

        def search_web(query: str) -> str:
            """Search the web for latest external docs, SDK guidance, and best practices."""

            tracked.web_search_attempted = True
            try:
                response = self.search_client.search_web(
                    query,
                    max_results=self.settings.search.default_max_results,
                )
            except Exception as exc:  # pragma: no cover
                tracked.web_search_error = str(exc)
                return f"Web search failed: {exc}"

            tracked.web_results = response.results
            tracked.web_search_error = response.error
            if not response.results:
                return response.error or "No web results."
            return "\n\n".join(
                f"{item.title}\nURL: {item.url}\nSnippet: {item.snippet}"
                for item in response.results
            )

        def search_knowledge_base(query: str) -> str:
            """Search the local knowledge base for project docs, coding guidance, and templates."""

            snippets = self.knowledge_base.search(query, limit=self.settings.rag.top_k)
            tracked.local_snippets = snippets
            tracked.retrieved_sources = [item.source_name for item in snippets]
            if not snippets:
                return "No local knowledge base matches."
            return "\n\n".join(
                f"{item.source_name}\nScore: {item.score:.3f}\n{item.excerpt}"
                for item in snippets
            )

        skills = []
        if skill_sources:
            skills.extend(skill_sources)

        return create_deep_agent(
            model=self._build_model(),
            tools=[search_web, search_knowledge_base, delete_file, run_command],
            system_prompt=self._system_prompt(
                workspace_root,
                target_root,
                target_root_virtual,
                tracked.matched_skills,
            ),
            skills=skills or None,
            backend=backend,
            debug=False,
            name="DevMate DeepAgent",
        )

    def _build_model(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.settings.model.model_name,
            api_key=self.settings.model.api_key,
            base_url=self.settings.model.ai_base_url,
            timeout=120,
            max_retries=1,
        )

    @staticmethod
    def _system_prompt(
        workspace_root: Path,
        target_root: Path,
        target_root_virtual: str,
        matched_skills: list[str],
    ) -> str:
        skill_hint = (
            f"Likely relevant skills already available to inspect: {', '.join(matched_skills)}. "
            if matched_skills
            else ""
        )
        return (
            "You are DevMate, a coding agent that must use filesystem tools to make real changes. "
            f"The active workspace root is {workspace_root.as_posix()}. "
            f"The preferred output target for this task is {target_root.as_posix()}. "
            f"When using filesystem tools, refer to that target as the virtual path {target_root_virtual}. "
            "When the user asks to build, edit, or fix code, do not only describe a plan. "
            "Use the available filesystem tools to inspect files, write files, edit files, and delete files when needed. "
            "If the task asks to verify behavior, run checks, or execute code, use run_command or the built-in execute capability. "
            "Use search_web for up-to-date external information and search_knowledge_base for project-specific guidance. "
            f"{skill_hint}"
            "When finished, provide a concise summary of what changed."
        )

    @staticmethod
    def _compose_user_prompt(
        prompt: str,
        *,
        workspace_root: Path,
        target_root: Path,
        target_root_virtual: str,
    ) -> str:
        return (
            f"Workspace root: {workspace_root.as_posix()}\n"
            f"Preferred output target: {target_root.as_posix()}\n"
            f"Preferred output target virtual path: {target_root_virtual}\n"
            "When calling filesystem tools, always use virtual paths that start with '/'.\n"
            "Complete the task by making real file changes when needed.\n\n"
            f"Task:\n{prompt}"
        )

    @staticmethod
    def _extract_assistant_text(result: object) -> str:
        if not isinstance(result, dict):
            return ""
        messages = result.get("messages")
        if not isinstance(messages, list):
            return ""
        for message in reversed(messages):
            content = getattr(message, "content", "")
            text = DeepAgentsRuntime._message_text(content)
            if text:
                return DeepAgentsRuntime._strip_think_blocks(text)
        return ""

    @staticmethod
    def _message_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(part for part in parts if part.strip())
        return ""

    @staticmethod
    def _strip_think_blocks(text: str) -> str:
        return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()

    def _updates_to_events(
        self,
        update: dict[str, object],
        *,
        tracked: _TrackedState,
        tool_call_args: dict[str, dict[str, object]],
        before_snapshot: dict[str, str],
    ) -> Iterator[dict[str, object]]:
        for node_name, payload in update.items():
            if not isinstance(payload, dict):
                continue
            messages = payload.get("messages")
            if not isinstance(messages, list):
                continue
            if node_name == "model":
                for message in messages:
                    for tool_call in getattr(message, "tool_calls", []) or []:
                        tool_name = str(tool_call.get("name") or "tool")
                        tool_id = str(tool_call.get("id") or "")
                        args = tool_call.get("args") or {}
                        if isinstance(args, dict):
                            tool_call_args[tool_id] = args
                        yield {
                            "type": "planning",
                            "step": {
                                "id": f"tool-{tool_id or tool_name}",
                                "title": f"Call {tool_name}",
                                "description": self._tool_description(tool_name, args),
                                "status": "running",
                            },
                        }
            elif node_name == "tools":
                for message in messages:
                    tool_name = str(getattr(message, "name", "") or "tool")
                    tool_call_id = str(getattr(message, "tool_call_id", "") or "")
                    content = str(getattr(message, "content", "") or "")
                    args = tool_call_args.get(tool_call_id, {})
                    yield {
                        "type": "planning",
                        "step": {
                            "id": f"tool-{tool_call_id or tool_name}",
                            "title": f"Call {tool_name}",
                            "description": self._tool_description(tool_name, args),
                            "status": "completed",
                            "output": content[:400],
                        },
                    }
                    if tool_name == "search_web" and tracked.web_results:
                        yield {
                            "type": "search",
                            "results": [
                                {
                                    "id": f"web-{index}",
                                    "title": item.title,
                                    "content": item.snippet,
                                    "source": "web",
                                    "score": float(item.score or 0.6),
                                    "url": item.url,
                                }
                                for index, item in enumerate(tracked.web_results)
                            ],
                        }
                    if tool_name == "search_knowledge_base" and tracked.local_snippets:
                        yield {
                            "type": "search",
                            "results": [
                                {
                                    "id": f"local-{index}",
                                    "title": item.source_name,
                                    "content": item.excerpt,
                                    "source": "local",
                                    "score": float(item.score),
                                }
                                for index, item in enumerate(tracked.local_snippets)
                            ],
                        }
                    file_node = self._tool_message_to_file_event(
                        tool_name,
                        args,
                        before_snapshot=before_snapshot,
                    )
                    if file_node is not None:
                        yield {"type": "file", "file": file_node}

    @staticmethod
    def _tool_description(tool_name: str, args: object) -> str:
        if tool_name in {"write_file", "edit_file", "read_file", "delete_file"} and isinstance(args, dict):
            path = args.get("file_path") or args.get("path") or "target file"
            return f"{tool_name} on {path}"
        if tool_name == "run_command":
            command = args.get("command") if isinstance(args, dict) else None
            return f"run command: {command or 'workspace command'}"
        if tool_name == "execute":
            command = args.get("command") if isinstance(args, dict) else None
            return f"execute command: {command or 'shell command'}"
        if tool_name == "search_web":
            return "Search external sources for current guidance."
        if tool_name == "search_knowledge_base":
            return "Search the local knowledge base."
        return f"Execute tool {tool_name}."

    @staticmethod
    def _tool_message_to_file_event(
        tool_name: str,
        args: dict[str, object],
        *,
        before_snapshot: dict[str, str],
    ) -> dict[str, object] | None:
        if tool_name not in {"write_file", "edit_file", "delete_file"}:
            return None
        raw_path = str(args.get("file_path") or args.get("path") or "")
        normalized = raw_path.lstrip("/")
        if not normalized:
            return None
        return {
            "name": Path(normalized).name,
            "path": normalized,
            "type": "file",
            "status": (
                "deleted"
                if tool_name == "delete_file"
                else "modified" if normalized in before_snapshot else "new"
            ),
        }

    def _workspace_root(self, target_root: Path) -> Path:
        from os.path import commonpath

        candidates = [Path.cwd().resolve(), target_root.resolve()]
        skills_dir = Path(self.settings.skills.skills_dir)
        if not skills_dir.is_absolute():
            skills_dir = (Path.cwd() / skills_dir).resolve()
        candidates.append(skills_dir)
        return Path(commonpath([str(candidate) for candidate in candidates]))

    @staticmethod
    def _virtual_target_path(workspace_root: Path, target_root: Path) -> str:
        try:
            relative = target_root.resolve().relative_to(workspace_root.resolve()).as_posix()
        except ValueError:
            return "/"
        return f"/{relative}".rstrip("/") if relative else "/"

    def _skills_sources(self, workspace_root: Path) -> list[str]:
        skills_dir = Path(self.settings.skills.skills_dir)
        if not skills_dir.is_absolute():
            skills_dir = (Path.cwd() / skills_dir).resolve()
        if not skills_dir.exists():
            return []
        try:
            relative = skills_dir.relative_to(workspace_root.resolve()).as_posix().strip("/")
        except ValueError:
            return []
        return [f"/{relative}/"] if relative else ["/"]

    @staticmethod
    def _load_deepagents_skills(
        backend: LocalShellBackend,
        skill_sources: list[str],
    ) -> list[SkillMetadata]:
        skills: dict[str, SkillMetadata] = {}
        for source in skill_sources:
            for item in _list_skills(backend, source):
                skills[item["name"]] = item
        return list(skills.values())

    @staticmethod
    def _rank_skill_candidates(
        skills: list[SkillMetadata],
        prompt: str,
        limit: int = 3,
    ) -> list[SkillMetadata]:
        terms = [term.lower() for term in re.findall(r"[a-zA-Z0-9_]+", prompt) if term.strip()]
        if not terms:
            return skills[:limit]
        scored: list[tuple[int, SkillMetadata]] = []
        for item in skills:
            haystack = f"{item['name']} {item['description']}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
        return [item for _, item in scored[:limit]]

    @staticmethod
    def _snapshot_files(root_dir: Path) -> dict[str, str]:
        if not root_dir.exists():
            return {}
        snapshot: dict[str, str] = {}
        for path in sorted(root_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root_dir).as_posix()
            snapshot[relative] = path.read_text(encoding="utf-8", errors="ignore")
        return snapshot

    @staticmethod
    def _diff_files(
        before: dict[str, str],
        after: dict[str, str],
    ) -> tuple[list[str], list[str], list[str]]:
        created = sorted(path for path in after if path not in before)
        modified = sorted(
            path for path, content in after.items() if path in before and before[path] != content
        )
        deleted = sorted(path for path in before if path not in after)
        return created, modified, deleted

    @staticmethod
    def _summarize_result(prompt: str, assistant_text: str, generated_files: list[str]) -> str:
        if assistant_text:
            first = assistant_text.splitlines()[0].strip()
            if first:
                return first
        if generated_files:
            return f"Updated {len(generated_files)} file(s) for: {prompt}"
        return f"Processed task: {prompt}"

    @staticmethod
    def _extract_steps(assistant_text: str, generated_files: list[str]) -> list[str]:
        steps: list[str] = []
        for line in assistant_text.splitlines():
            stripped = line.strip()
            if re.match(r"^(-|\*|\d+\.)\s+", stripped):
                steps.append(re.sub(r"^(-|\*|\d+\.)\s+", "", stripped))
        if steps:
            return steps[:8]
        if generated_files:
            return [
                "Inspect the target workspace and relevant files.",
                "Use deepagents filesystem tools to apply the requested changes.",
                "Review the written files and summarize the result.",
            ]
        return ["Run the task through deepagents and summarize the outcome."]

    @staticmethod
    def _planned_files_from_text(assistant_text: str) -> list[str]:
        matches = re.findall(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]+", assistant_text)
        deduped: list[str] = []
        for item in matches:
            if item not in deduped:
                deduped.append(item)
        return deduped[:12]

    def _model_is_configured(self) -> bool:
        key = self.settings.model.api_key.strip()
        model = self.settings.model.model_name.strip()
        return bool(key and model and "your_" not in key.lower())

    @staticmethod
    def _build_skill_note(
        name: str,
        prompt: str,
        summary: str,
        steps: list[str],
    ) -> SkillNote:
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
            summary=summary,
            steps=steps[:12],
            keywords=deduped_keywords[:8],
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
                generated_deleted_files=result.generated_deleted_files or [],
                generation_used_model=result.generation_used_model,
                generation_error=result.generation_error,
                saved_skill_path=result.saved_skill_path,
            ),
        )

    @staticmethod
    def _render_assistant_message(result: PromptResult) -> str:
        parts = [result.summary]
        if result.generated_files:
            parts.extend(["", "Changed files:"])
            parts.extend(f"- {path}" for path in result.generated_files)
        if result.implementation_steps:
            parts.extend(["", "Implementation steps:"])
            parts.extend(f"- {step}" for step in result.implementation_steps)
        if result.agent_error:
            parts.extend(["", f"Runtime warning: {result.agent_error}"])
        return "\n".join(parts)

    @staticmethod
    def _chunk_content(text: str, chunk_size: int = 120) -> Iterator[str]:
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
