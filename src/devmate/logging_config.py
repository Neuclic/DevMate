"""Logging helpers for DevMate."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure application logging once at process startup."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
