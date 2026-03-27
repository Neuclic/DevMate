"""Tests for web-search trigger heuristics."""

from __future__ import annotations

from devmate.search_policy import should_search_web


def test_search_policy_triggers_for_latest_info() -> None:
    assert should_search_web("latest FastAPI release notes") is True
    assert should_search_web("查询最新的 React 版本和变更日志") is True


def test_search_policy_triggers_for_recommendations_and_comparisons() -> None:
    assert should_search_web("Leaflet vs Mapbox comparison for a map website") is True
    assert should_search_web("给我推荐一个适合小游戏的 canvas 方案") is True


def test_search_policy_triggers_for_web_game_generation_prompts() -> None:
    assert should_search_web("build a flappy bird web game") is True
    assert should_search_web("build a browser game with html css and javascript") is True


def test_search_policy_does_not_trigger_for_local_only_refactors() -> None:
    assert should_search_web("rename this variable in the current file") is False
    assert should_search_web("fix a typo in the current module") is False
