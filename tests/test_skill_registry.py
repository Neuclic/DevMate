"""Tests for saved skill registry behavior."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from devmate.skill_registry import SkillNote, SkillRegistry


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = WORKSPACE_ROOT / "tests" / "fixtures" / "anthropic_skills"


def _make_test_root() -> Path:
    root = WORKSPACE_ROOT / "test_scratch" / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_skill_registry_saves_and_loads_skill_notes() -> None:
    root = _make_test_root()
    try:
        registry = SkillRegistry(root / ".skills")
        saved_path = registry.save(
            SkillNote(
                name="Build Static Site",
                summary="Use this for static website delivery.",
                steps=["Split files.", "Add local verification."],
                keywords=["website", "frontend"],
                tools=["search_local_knowledge"],
            )
        )
        loaded = registry.load("Build Static Site")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert saved_path.name == "SKILL.md"
    assert saved_path.parent.name == "build-static-site"
    assert loaded is not None
    assert loaded.name == "Build Static Site"
    assert loaded.keywords == ["website", "frontend"]
    assert loaded.tools == ["search_local_knowledge"]
    assert loaded.steps[0] == "Split files."


def test_skill_registry_search_returns_relevant_skills() -> None:
    root = _make_test_root()
    try:
        registry = SkillRegistry(root / ".skills")
        registry.save(
            SkillNote(
                name="Build Static Site",
                summary="Use this for static website delivery.",
                steps=["Split files.", "Add local verification."],
                keywords=["website", "frontend"],
            )
        )
        registry.save(
            SkillNote(
                name="Package Docker Delivery",
                summary="Use this for Docker handoff.",
                steps=["Write Dockerfile.", "Add compose file."],
                keywords=["docker", "container"],
            )
        )
        matches = registry.search("frontend website", limit=2)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    assert len(matches) == 1
    assert matches[0].name == "Build Static Site"


def test_skill_registry_loads_anthropic_style_skill_directories() -> None:
    registry = SkillRegistry(FIXTURES_ROOT)

    matches = registry.search("browser qa webapp", limit=2)
    loaded = registry.load("webapp-testing")
    context = registry.load_context("webapp-testing")

    assert len(matches) == 1
    assert matches[0].name == "Webapp Testing"
    assert loaded is not None
    assert loaded.slug == "webapp-testing"
    assert loaded.tools == ["search_local_knowledge"]
    assert context is not None
    assert "Checklist" in context
    assert "browser-oriented QA pass" in context