"""MCP client for calling the local search server over Streamable HTTP."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse, urlunparse

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult
from langsmith.run_helpers import traceable

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    """Search result returned by the MCP layer."""

    title: str
    url: str
    snippet: str
    score: float | None = None


@dataclass(frozen=True)
class SearchResponse:
    """Normalized search response from the MCP server."""

    query: str
    results: list[SearchResult]
    answer: str | None = None
    response_time: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class SearchMcpClient:
    """Configuration for the MCP search client."""

    server_url: str
    transport: str
    tool_timeout_seconds: float = 30.0
    healthcheck_timeout_seconds: float = 5.0

    async def healthcheck_async(self) -> None:
        """Verify the configured MCP server is reachable before calling tools."""
        health_url = self._healthcheck_url()
        timeout = httpx.Timeout(self.healthcheck_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(health_url)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"MCP server health check timed out after {self.healthcheck_timeout_seconds} seconds."
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Unable to reach MCP server health endpoint: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MCP server health endpoint returned status {exc.response.status_code}."
            ) from exc

        LOGGER.info("MCP health check passed at %s", health_url)

    @traceable(run_type="tool", name="search_web_mcp")
    async def search_web_async(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
    ) -> SearchResponse:
        """Call the configured MCP server and execute the search_web tool."""
        if self.transport not in {"streamable_http", "streamable-http", "http"}:
            raise ValueError(
                "SearchMcpClient currently supports only Streamable HTTP transport."
            )

        await self.healthcheck_async()
        LOGGER.info(
            "Calling MCP tool search_web query='%s' max_results=%d depth='%s'",
            query,
            max_results,
            search_depth,
        )

        try:
            async with streamable_http_client(self.server_url) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "search_web",
                        {
                            "query": query,
                            "max_results": max_results,
                            "search_depth": search_depth,
                            "topic": topic,
                        },
                        read_timeout_seconds=timedelta(seconds=self.tool_timeout_seconds),
                    )
        except RuntimeError:
            raise
        except Exception as exc:
            LOGGER.exception("MCP tool call failed for query='%s'", query)
            raise RuntimeError(f"MCP tool call failed: {exc}") from exc

        parsed = self._parse_result(result, query)
        LOGGER.info(
            "MCP tool search_web completed query='%s' results=%d",
            parsed.query,
            len(parsed.results),
        )
        return parsed

    def search_web(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
    ) -> SearchResponse:
        """Synchronous wrapper around the async search client."""
        return asyncio.run(
            self.search_web_async(
                query,
                max_results=max_results,
                search_depth=search_depth,
                topic=topic,
            )
        )

    @staticmethod
    def _parse_result(result: CallToolResult, fallback_query: str) -> SearchResponse:
        """Normalize an MCP CallToolResult into local response models."""
        if result.isError:
            raise RuntimeError(SearchMcpClient._extract_error_message(result))

        payload = result.structuredContent or {}
        items = [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                score=item.get("score"),
            )
            for item in payload.get("results", [])
        ]
        return SearchResponse(
            query=payload.get("query", fallback_query),
            results=items,
            answer=payload.get("answer"),
            response_time=payload.get("response_time"),
            error=payload.get("error"),
        )

    @staticmethod
    def _extract_error_message(result: CallToolResult) -> str:
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(str(block))
        return " | ".join(parts) or "MCP tool call failed."

    def _healthcheck_url(self) -> str:
        parsed = urlparse(self.server_url)
        return urlunparse((parsed.scheme, parsed.netloc, "/health", "", "", ""))
