"""Unit tests for MCP helpers."""

from __future__ import annotations

import mcp.types as mcp_types

from devmate.mcp_client import SearchMcpClient
from devmate.mcp_server import parse_mcp_server_url


def test_parse_mcp_server_url_keeps_host_port_and_path() -> None:
    endpoint = parse_mcp_server_url("http://localhost:8001/mcp")

    assert endpoint.host == "localhost"
    assert endpoint.port == 8001
    assert endpoint.path == "/mcp"


def test_parse_client_structured_result() -> None:
    result = mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "query": "fastapi",
            "results": [
                {
                    "title": "FastAPI",
                    "url": "https://fastapi.tiangolo.com/",
                    "snippet": "FastAPI documentation",
                    "score": 0.99,
                }
            ],
            "response_time": 0.42,
        },
    )

    response = SearchMcpClient._parse_result(result, "fallback")

    assert response.query == "fastapi"
    assert len(response.results) == 1
    assert response.results[0].title == "FastAPI"
    assert response.results[0].score == 0.99


def test_healthcheck_url_uses_server_origin() -> None:
    client = SearchMcpClient(
        server_url="http://localhost:8001/mcp",
        transport="streamable_http",
    )

    assert client._healthcheck_url() == "http://localhost:8001/health"
