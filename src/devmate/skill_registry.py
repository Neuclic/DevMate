"""Helpers for storing reusable skill notes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class SkillNote:
    """A reusable note describing a successful task pattern."""

    name: str
    summary: str
    steps: list[str]


class SkillRegistry:
    """Persist skill notes as markdown files."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir

    def save(self, note: SkillNote) -> Path:
        """Save a skill note to disk."""
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        slug = self._slugify(note.name)
        target = self.skills_dir / f"{slug}.md"
        lines = [
            f"# {note.name}",
            "",
            note.summary,
            "",
            "## Steps",
            "",
        ]
        lines.extend(f"- {step}" for step in note.steps)
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
        return normalized.strip("-") or "skill-note"
