"""Placeholder structures for the future MCP server implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchToolDefinition:
    """Metadata for the MCP search tool."""

    name: str = "search_web"
    description: str = "Search the public web through Tavily."
