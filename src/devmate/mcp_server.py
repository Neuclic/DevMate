"""MCP server implementation for Tavily-backed web search."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.server import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from devmate.config_loader import AppSettings

LOGGER = logging.getLogger(__name__)
TAVILY_API_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class SearchToolDefinition:
    """Metadata for the MCP search tool."""

    name: str = "search_web"
    description: str = "Search the public web through Tavily."


@dataclass(frozen=True)
class McpEndpoint:
    """Normalized Streamable HTTP endpoint settings."""

    host: str
    port: int
    path: str


@dataclass(frozen=True)
class TavilySearchBackend:
    """Thin async client for Tavily Search."""

    api_key: str
    timeout_seconds: float

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
    ) -> dict[str, Any]:
        """Execute a Tavily search and normalize the response payload."""
        if not self.api_key or self.api_key.startswith("your_"):
            raise RuntimeError(
                "Tavily API key is not configured. "
                "Update [search].tavily_api_key in config.toml."
            )

        LOGGER.info(
            "Dispatching Tavily search query='%s' topic='%s' depth='%s' max_results=%d",
            query,
            topic,
            search_depth,
            max_results,
        )
        payload = {
            "query": query,
            "topic": topic,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            timeout = httpx.Timeout(self.timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(TAVILY_API_URL, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            LOGGER.exception("Tavily search timed out for query='%s'", query)
            raise RuntimeError(
                f"Tavily search timed out after {self.timeout_seconds} seconds."
            ) from exc
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text[:500]
            LOGGER.exception(
                "Tavily search failed with status=%s for query='%s'",
                exc.response.status_code,
                query,
            )
            raise RuntimeError(
                "Tavily search request failed with status "
                f"{exc.response.status_code}: {response_text}"
            ) from exc
        except httpx.RequestError as exc:
            LOGGER.exception("Tavily search request error for query='%s'", query)
            raise RuntimeError(f"Tavily search request error: {exc}") from exc

        data = response.json()
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "score": item.get("score"),
            }
            for item in data.get("results", [])
        ]
        LOGGER.info(
            "Tavily search completed query='%s' results=%d response_time=%s",
            query,
            len(results),
            data.get("response_time"),
        )
        return {
            "query": data.get("query", query),
            "answer": data.get("answer"),
            "results": results,
            "response_time": data.get("response_time"),
        }


def parse_mcp_server_url(server_url: str) -> McpEndpoint:
    """Parse the configured MCP URL into FastMCP host/port/path settings."""
    parsed = urlparse(server_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"Invalid MCP server URL: {server_url}")

    if parsed.scheme == "https":
        default_port = 443
    else:
        default_port = 80

    return McpEndpoint(
        host=parsed.hostname,
        port=parsed.port or default_port,
        path=parsed.path or "/mcp",
    )


def create_search_mcp_server(settings: AppSettings) -> FastMCP:
    """Create a FastMCP server exposing the Tavily-backed search tool."""
    endpoint = parse_mcp_server_url(settings.mcp.server_url)
    backend = TavilySearchBackend(
        api_key=settings.search.tavily_api_key,
        timeout_seconds=settings.search.request_timeout_seconds,
    )
    server = FastMCP(
        name="DevMate Search MCP",
        instructions=(
            "Use the search_web tool to retrieve up-to-date public web results "
            "through Tavily."
        ),
        host=endpoint.host,
        port=endpoint.port,
        streamable_http_path=endpoint.path,
        log_level=settings.app.log_level,
    )

    @server.tool(
        name=SearchToolDefinition.name,
        description=SearchToolDefinition.description,
        structured_output=True,
    )
    async def search_web(
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
    ) -> dict[str, Any]:
        """Search the web through Tavily and return structured results."""
        bounded_results = max(1, min(max_results, 20))
        try:
            return await backend.search(
                query,
                max_results=bounded_results,
                search_depth=search_depth,
                topic=topic,
            )
        except RuntimeError:
            LOGGER.exception("search_web tool failed for query='%s'", query)
            raise

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> Response:
        return JSONResponse(
            {
                "status": "ok",
                "transport": "streamable_http",
                "server_url": settings.mcp.server_url,
                "tavily_configured": not settings.search.tavily_api_key.startswith("your_"),
            }
        )

    return server


def _assert_endpoint_available(endpoint: McpEndpoint) -> None:
    """Fail fast with a clear error when the configured port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex((endpoint.host, endpoint.port))

    if result == 0:
        raise RuntimeError(
            "MCP server cannot start because "
            f"{endpoint.host}:{endpoint.port} is already in use."
        )


def run_mcp_server(settings: AppSettings) -> None:
    """Run the Tavily-backed MCP server over Streamable HTTP."""
    endpoint = parse_mcp_server_url(settings.mcp.server_url)
    _assert_endpoint_available(endpoint)
    key_prefix = settings.search.tavily_api_key[:6] if settings.search.tavily_api_key else ""
    LOGGER.info(
        "Starting MCP server at %s with Tavily key configured=%s prefix=%s***",
        settings.mcp.server_url,
        bool(settings.search.tavily_api_key and not settings.search.tavily_api_key.startswith("your_")),
        key_prefix,
    )
    server = create_search_mcp_server(settings)
    server.run(transport="streamable-http")
