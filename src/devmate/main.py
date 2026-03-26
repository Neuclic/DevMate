"""CLI entry point for the DevMate skeleton."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from devmate.agent_runtime import DevMateRuntime
from devmate.config_loader import load_settings
from devmate.logging_config import configure_logging

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
    return parser


def main() -> int:
    """Run the CLI application."""
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)
    settings = load_settings(Path(args.config))
    runtime = DevMateRuntime(settings=settings)

    if args.prompt:
        result = runtime.handle_prompt(args.prompt)
        LOGGER.info("Prompt summary: %s", result.summary)
        LOGGER.info("Planned files: %s", ", ".join(result.planned_files))
        return 0

    LOGGER.info("DevMate skeleton is ready.")
    LOGGER.info("Project name: %s", settings.app.project_name)
    LOGGER.info("Provide --prompt to simulate one planning run.")
    return 0
