"""Helpers for storing and retrieving reusable skill notes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass(frozen=True)
class SkillNote:
    """A reusable note describing a successful task pattern."""

    name: str
    summary: str
    steps: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    slug: str | None = None
    source_path: str | None = None
    content: str | None = None


class SkillRegistry:
    """Persist and retrieve skills in a SKILL.md-centric directory layout."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir

    def save(self, note: SkillNote) -> Path:
        """Save a skill note to disk using the official-style folder layout."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        slug = note.slug or self._slugify(note.name)
        target_dir = self.skills_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "SKILL.md"
        lines = [
            "---",
            f"name: {note.name}",
            f"description: {note.summary.strip()}",
        ]
        if note.keywords:
            lines.append("keywords:")
            lines.extend(f"  - {keyword.strip()}" for keyword in note.keywords if keyword.strip())
        if note.tools:
            lines.append("tools:")
            lines.extend(f"  - {tool.strip()}" for tool in note.tools if tool.strip())
        lines.extend(
            [
                "---",
                "",
                f"# {note.name}",
                "",
                "## Summary",
                "",
                note.summary.strip(),
                "",
                "## Steps",
                "",
            ]
        )
        lines.extend(f"{index}. {step}" for index, step in enumerate(note.steps, start=1))
        target.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return target

    def list_skills(self) -> list[SkillNote]:
        """Return all stored skills."""
        notes: list[SkillNote] = []
        for path in self._iter_skill_paths():
            note = self._load_path(path, include_content=False)
            if note is not None:
                notes.append(note)
        return notes

    def search(self, query: str, limit: int = 3) -> list[SkillNote]:
        """Search saved skills by metadata overlap."""
        terms = [term.lower() for term in re.findall(r"[a-zA-Z0-9_]+", query) if term.strip()]
        if not terms:
            return self.list_skills()[:limit]

        scored: list[tuple[float, SkillNote]] = []
        for note in self.list_skills():
            haystack = " ".join(
                [
                    note.name,
                    note.summary,
                    " ".join(note.steps),
                    " ".join(note.keywords),
                    " ".join(note.tools),
                    note.slug or "",
                ]
            ).lower()
            score = float(sum(haystack.count(term) for term in terms))
            if score <= 0:
                continue
            scored.append((score, note))

        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [note for _, note in scored[:limit]]

    def load(self, name_or_slug: str) -> SkillNote | None:
        """Load one saved skill by display name or slug."""
        target_slug = self._slugify(name_or_slug)
        for path in self._iter_skill_paths():
            note = self._load_path(path, include_content=True)
            if note is None:
                continue
            candidates = {
                self._slugify(note.name),
                note.slug or "",
                target_slug,
            }
            if target_slug in candidates or self._slugify(note.name) == target_slug:
                return note
        return None

    def load_context(self, name_or_slug: str) -> str | None:
        """Load full skill context, including supporting markdown/text files."""
        note = self.load(name_or_slug)
        if note is None or note.source_path is None:
            return None

        skill_path = Path(note.source_path)
        skill_root = skill_path.parent
        blocks = [note.content.strip() if note.content else ""]
        for path in sorted(skill_root.rglob("*")):
            if not path.is_file() or path.name == "SKILL.md":
                continue
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            relative = path.relative_to(skill_root)
            blocks.append(f"[FILE: {relative.as_posix()}]\n{path.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(block for block in blocks if block.strip()) or None

    def _iter_skill_paths(self) -> list[Path]:
        if not self.skills_dir.exists():
            return []
        official = sorted(
            path for path in self.skills_dir.rglob("SKILL.md") if path.is_file()
        )
        legacy = sorted(
            path
            for path in self.skills_dir.glob("*.md")
            if path.is_file() and path.name.lower() != "readme.md"
        )
        seen: set[Path] = set()
        ordered: list[Path] = []
        for path in official + legacy:
            if path in seen:
                continue
            seen.add(path)
            ordered.append(path)
        return ordered

    def _load_path(self, path: Path, *, include_content: bool) -> SkillNote | None:
        raw = path.read_text(encoding="utf-8").strip()
        if path.name == "SKILL.md":
            return self._load_official_skill(path, raw, include_content=include_content)
        return self._load_legacy_skill(path, raw, include_content=include_content)

    def _load_official_skill(self, path: Path, raw: str, *, include_content: bool) -> SkillNote | None:
        frontmatter, body = self._split_frontmatter(raw)
        metadata = self._parse_frontmatter(frontmatter)
        if not body.strip():
            return None

        name = metadata.get("name") or self._extract_heading(body) or path.parent.name
        summary = metadata.get("description") or self._extract_section(body, "summary") or ""
        steps = self._extract_steps(body)
        keywords = self._parse_list_value(metadata.get("keywords", ""))
        tools = self._parse_list_value(metadata.get("tools", ""))
        slug = path.parent.name
        return SkillNote(
            name=name,
            summary=summary,
            steps=steps,
            keywords=keywords,
            tools=tools,
            slug=slug,
            source_path=str(path.resolve()),
            content=body if include_content else None,
        )

    def _load_legacy_skill(self, path: Path, raw: str, *, include_content: bool) -> SkillNote | None:
        if not raw.startswith("# "):
            return None

        lines = raw.splitlines()
        name = lines[0][2:].strip()
        sections = self._parse_sections(lines[1:])
        summary = "\n".join(sections.get("summary", [])).strip()
        keywords_raw = " ".join(sections.get("keywords", [])).strip()
        keywords = [item.strip() for item in keywords_raw.split(",") if item.strip()]
        steps = [self._normalize_step(line) for line in sections.get("steps", []) if line.strip()]
        return SkillNote(
            name=name,
            summary=summary,
            steps=steps,
            keywords=keywords,
            slug=path.stem,
            source_path=str(path.resolve()),
            content=raw if include_content else None,
        )

    @staticmethod
    def _split_frontmatter(raw: str) -> tuple[str, str]:
        stripped = raw.strip()
        if not stripped.startswith("---\n"):
            return "", raw
        parts = stripped.split("\n---\n", 1)
        if len(parts) != 2:
            return "", raw
        frontmatter = parts[0][4:]
        body = parts[1]
        return frontmatter, body

    @staticmethod
    def _parse_frontmatter(frontmatter: str) -> dict[str, str]:
        data: dict[str, str] = {}
        current_key: str | None = None
        list_buffer: list[str] = []
        for line in frontmatter.splitlines():
            if not line.strip():
                continue
            if re.match(r"^[A-Za-z0-9_-]+:\s*$", line):
                if current_key is not None and list_buffer:
                    data[current_key] = "\n".join(list_buffer)
                current_key = line.split(":", 1)[0].strip().lower()
                list_buffer = []
                continue
            if current_key and line.lstrip().startswith("- "):
                list_buffer.append(line.split("- ", 1)[1].strip())
                continue
            key, _, value = line.partition(":")
            if key and _:
                if current_key is not None and list_buffer:
                    data[current_key] = "\n".join(list_buffer)
                    list_buffer = []
                current_key = None
                data[key.strip().lower()] = value.strip().strip('"')
        if current_key is not None and list_buffer:
            data[current_key] = "\n".join(list_buffer)
        return data

    @staticmethod
    def _parse_list_value(value: str) -> list[str]:
        if not value:
            return []
        if "\n" in value:
            return [item.strip() for item in value.splitlines() if item.strip()]
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _extract_heading(body: str) -> str | None:
        for line in body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    @staticmethod
    def _extract_section(body: str, name: str) -> str:
        pattern = re.compile(rf"^##\s+{re.escape(name)}\s*$", re.IGNORECASE | re.MULTILINE)
        match = pattern.search(body)
        if not match:
            return ""
        start = match.end()
        next_header = re.search(r"^##\s+", body[start:], re.MULTILINE)
        section = body[start : start + next_header.start()] if next_header else body[start:]
        return "\n".join(line for line in section.splitlines() if line.strip()).strip()

    def _extract_steps(self, body: str) -> list[str]:
        steps_section = self._extract_section(body, "steps")
        if not steps_section:
            return []
        return [self._normalize_step(line) for line in steps_section.splitlines() if line.strip()]

    @staticmethod
    def _parse_sections(lines: list[str]) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current = "summary"
        buffer: list[str] = []

        for line in lines:
            if line.startswith("## "):
                sections[current] = [item for item in buffer if item.strip()]
                current = line[3:].strip().lower()
                buffer = []
                continue
            buffer.append(line)

        sections[current] = [item for item in buffer if item.strip()]
        return sections

    @staticmethod
    def _normalize_step(line: str) -> str:
        normalized = re.sub(r"^\d+\.\s*", "", line.strip())
        normalized = re.sub(r"^-\s*", "", normalized)
        return normalized.strip()

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
        return normalized.strip("-") or "skill-note"