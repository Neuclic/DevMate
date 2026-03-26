"""CLI entry point for the DevMate skeleton."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import load_settings
from devmate.logging_config import configure_logging
from devmate.mcp_client import SearchMcpClient
from devmate.mcp_server import run_mcp_server

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="DevMate project skeleton")
    parser.add_argument(
        "--config",
        default="config.toml",
        help="Path to the TOML configuration file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Application log level.",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="Optional prompt used to simulate one agent run.",
    )
    parser.add_argument(
        "--serve-mcp",
        action="store_true",
        help="Run the local MCP server using the configured Streamable HTTP endpoint.",
    )
    parser.add_argument(
        "--mcp-query",
        default="",
        help="Send one query to the configured MCP server through the client.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of Tavily results to request through MCP.",
    )
    return parser


def main() -> int:
    """Run the CLI application."""
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)
    settings = load_settings(Path(args.config))

    if args.serve_mcp:
        run_mcp_server(settings)
        return 0

    if args.mcp_query:
        client = SearchMcpClient(
            server_url=settings.mcp.server_url,
            transport=settings.mcp.transport,
        )
        response = client.search_web(
            args.mcp_query,
            max_results=args.max_results,
        )
        LOGGER.info("MCP query: %s", response.query)
        LOGGER.info("MCP results: %d", len(response.results))
        for item in response.results:
            LOGGER.info("%s | %s", item.title, item.url)
        return 0

    runtime = DevMateRuntime(settings=settings)

    if args.prompt:
        result = runtime.handle_prompt(args.prompt)
        LOGGER.info("Prompt summary: %s", result.summary)
        LOGGER.info("Planned files: %s", ", ".join(result.planned_files))
        if result.retrieved_sources:
            LOGGER.info(
                "Local knowledge sources: %s",
                ", ".join(result.retrieved_sources),
            )
        if result.web_results:
            LOGGER.info("Web search results: %d", len(result.web_results))
            for item in result.web_results:
                LOGGER.info("%s | %s", item.title, item.url)
        elif result.web_search_error:
            LOGGER.warning("Web search error: %s", result.web_search_error)
        return 0

    LOGGER.info("DevMate skeleton is ready.")
    LOGGER.info("Project name: %s", settings.app.project_name)
    LOGGER.info("Provide --prompt to simulate one planning run.")
    return 0
