"""LangSmith observability helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import logging
import os

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client

from devmate.config_loader import AppSettings

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceInfo:
    """Resolved LangSmith trace information."""

    run_id: str
    project_name: str
    run_url: str
    shared_url: str | None = None


def is_placeholder(value: str) -> bool:
    """Return whether a config value still looks like a placeholder."""
    stripped = value.strip()
    return not stripped or stripped.lower().startswith("your_")


def langsmith_is_configured(settings: AppSettings) -> bool:
    """Return whether LangSmith tracing is effectively configured."""
    return (
        settings.langsmith.langchain_tracing_v2
        and not is_placeholder(settings.langsmith.langchain_api_key)
    )


def configure_langsmith(settings: AppSettings) -> bool:
    """Apply LangSmith environment configuration for the current process."""
    if not langsmith_is_configured(settings):
        LOGGER.info("LangSmith tracing is not configured. Skipping observability setup.")
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith.langchain_api_key
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith.project_name
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith.project_name
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith.endpoint
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith.endpoint
    LOGGER.info(
        "LangSmith tracing enabled project='%s' endpoint='%s'",
        settings.langsmith.project_name,
        settings.langsmith.endpoint,
    )
    return True


def trace_start_time() -> datetime:
    """Return a UTC timestamp suitable for querying recent runs."""
    return datetime.now(timezone.utc)


def latest_trace_info(
    settings: AppSettings,
    *,
    started_at: datetime,
    share_public: bool = False,
) -> TraceInfo | None:
    """Resolve the latest root trace URL for the current LangSmith project."""
    if not langsmith_is_configured(settings):
        return None

    wait_for_all_tracers()
    client = Client(
        api_key=settings.langsmith.langchain_api_key,
        api_url=settings.langsmith.endpoint,
    )
    runs = list(
        client.list_runs(
            project_name=settings.langsmith.project_name,
            is_root=True,
            start_time=started_at,
            limit=5,
        )
    )
    if not runs:
        LOGGER.warning(
            "LangSmith tracing is enabled, but no root run was found after %s.",
            started_at.isoformat(),
        )
        return None

    latest = max(runs, key=lambda run: getattr(run, "start_time", started_at))
    run_url = client.get_run_url(
        run=latest,
        project_name=settings.langsmith.project_name,
    )
    shared_url = client.share_run(latest.id) if share_public else None
    return TraceInfo(
        run_id=str(latest.id),
        project_name=settings.langsmith.project_name,
        run_url=run_url,
        shared_url=shared_url,
    )
