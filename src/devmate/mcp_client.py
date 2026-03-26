"""Placeholder MCP client abstractions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    """Search result returned by the MCP layer."""

    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SearchMcpClient:
    """Configuration for the MCP search client."""

    server_url: str
    transport: str

    def search_web(self, query: str) -> list[SearchResult]:
        """Return placeholder results until the real integration is added."""
        del query
        return []
