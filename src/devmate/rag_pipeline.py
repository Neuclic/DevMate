"""A lightweight local document search placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeSnippet:
    """A locally retrieved document snippet."""

    source_name: str
    excerpt: str
    score: int


class KnowledgeBasePipeline:
    """Simple keyword retrieval used before the real vector DB is added."""

    def __init__(self, docs_dir: Path) -> None:
        self.docs_dir = docs_dir

    def search(self, query: str, limit: int = 3) -> list[KnowledgeSnippet]:
        """Search markdown documents by keyword frequency."""
        if not self.docs_dir.exists():
            return []

        terms = [term.lower() for term in query.split() if term.strip()]
        matches: list[KnowledgeSnippet] = []

        for path in sorted(self.docs_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            lowered = content.lower()
            score = sum(lowered.count(term) for term in terms)
            if score == 0:
                continue
            excerpt = " ".join(content.split())[:280]
            matches.append(
                KnowledgeSnippet(
                    source_name=path.name,
                    excerpt=excerpt,
                    score=score,
                )
            )

        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]
