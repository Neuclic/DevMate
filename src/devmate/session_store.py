"""Persistent local session history for multi-turn runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug_from_prompt(prompt: str) -> str:
    cleaned = " ".join(prompt.split())
    if not cleaned:
        return "New Session"
    words = re.findall(r"[A-Za-z0-9_]+", cleaned)
    if not words:
        return cleaned[:40] or "New Session"
    return " ".join(words[:8])[:60]


@dataclass(frozen=True)
class ConversationTurn:
    """Compact turn representation used as planning context."""

    prompt: str
    assistant_summary: str


@dataclass(frozen=True)
class SessionTurn:
    """One persisted session turn."""

    turn_id: str
    created_at: str
    prompt: str
    assistant_summary: str
    planned_files: list[str] = field(default_factory=list)
    implementation_steps: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    retrieved_sources: list[str] = field(default_factory=list)
    web_results: list[dict[str, object]] = field(default_factory=list)
    web_search_attempted: bool = False
    web_search_error: str | None = None
    agent_used_model: bool = False
    agent_error: str | None = None
    generation_output_dir: str | None = None
    generated_files: list[str] = field(default_factory=list)
    generated_created_files: list[str] = field(default_factory=list)
    generated_modified_files: list[str] = field(default_factory=list)
    generation_used_model: bool = False
    generation_error: str | None = None
    saved_skill_path: str | None = None
    trace_url: str | None = None
    shared_trace_url: str | None = None


@dataclass(frozen=True)
class SessionRecord:
    """One persisted session record."""

    session_id: str
    title: str
    created_at: str
    updated_at: str
    turns: list[SessionTurn] = field(default_factory=list)


@dataclass(frozen=True)
class SessionSummary:
    """Compact metadata for one saved session."""

    session_id: str
    title: str
    updated_at: str
    turn_count: int


class SessionStore:
    """JSON-backed storage for multi-turn DevMate sessions."""

    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = sessions_dir

    def create_session(self, title: str | None = None) -> SessionRecord:
        """Create and persist an empty session."""
        session_id = uuid4().hex
        now = _utc_now()
        record = SessionRecord(
            session_id=session_id,
            title=title or "New Session",
            created_at=now,
            updated_at=now,
            turns=[],
        )
        self._write(record)
        return record

    def ensure_session(self, session_id: str, title: str | None = None) -> SessionRecord:
        """Return the existing session or create it on demand."""
        record = self.get_session(session_id)
        if record is not None:
            return record
        now = _utc_now()
        record = SessionRecord(
            session_id=session_id,
            title=title or "New Session",
            created_at=now,
            updated_at=now,
            turns=[],
        )
        self._write(record)
        return record

    def list_sessions(self) -> list[SessionSummary]:
        """Return all sessions sorted by most recently updated."""
        summaries: list[SessionSummary] = []
        for path in sorted(self.sessions_dir.glob("*.json")) if self.sessions_dir.exists() else []:
            record = self._read_path(path)
            if record is None:
                continue
            summaries.append(
                SessionSummary(
                    session_id=record.session_id,
                    title=record.title,
                    updated_at=record.updated_at,
                    turn_count=len(record.turns),
                )
            )
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Load one session record by id."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        return self._read_path(path)

    def append_turn(self, session_id: str, turn: SessionTurn) -> SessionRecord:
        """Append one new turn to a session and persist it."""
        record = self.ensure_session(session_id)
        title = record.title
        if title == "New Session" and not record.turns:
            title = _slug_from_prompt(turn.prompt)
        updated = SessionRecord(
            session_id=record.session_id,
            title=title,
            created_at=record.created_at,
            updated_at=_utc_now(),
            turns=[*record.turns, turn],
        )
        self._write(updated)
        return updated

    def build_conversation_history(
        self,
        session_id: str,
        *,
        limit: int = 6,
    ) -> list[ConversationTurn]:
        """Return the most recent turns as compact planning context."""
        record = self.get_session(session_id)
        if record is None:
            return []
        turns = record.turns[-limit:]
        return [
            ConversationTurn(
                prompt=turn.prompt,
                assistant_summary=turn.assistant_summary,
            )
            for turn in turns
        ]

    def update_latest_turn_trace(
        self,
        session_id: str,
        *,
        trace_url: str | None,
        shared_trace_url: str | None,
    ) -> SessionRecord | None:
        """Update the most recent turn with LangSmith trace links."""
        record = self.get_session(session_id)
        if record is None or not record.turns:
            return None

        latest = record.turns[-1]
        updated_turn = SessionTurn(
            **{
                **asdict(latest),
                "trace_url": trace_url,
                "shared_trace_url": shared_trace_url,
            }
        )
        updated = SessionRecord(
            session_id=record.session_id,
            title=record.title,
            created_at=record.created_at,
            updated_at=_utc_now(),
            turns=[*record.turns[:-1], updated_turn],
        )
        self._write(updated)
        return updated

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _write(self, record: SessionRecord) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self._session_path(record.session_id)
        path.write_text(
            json.dumps(asdict(record), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _read_path(path: Path) -> SessionRecord | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        turns = [
            SessionTurn(**item)
            for item in payload.get("turns", [])
            if isinstance(item, dict)
        ]
        return SessionRecord(
            session_id=str(payload.get("session_id", path.stem)),
            title=str(payload.get("title", "New Session")),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            turns=turns,
        )
