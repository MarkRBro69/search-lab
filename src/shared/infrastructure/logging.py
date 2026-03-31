"""Central structlog configuration (APP_ENV → console vs JSON)."""

from __future__ import annotations

import logging
import os

import structlog
from structlog.contextvars import merge_contextvars


def configure_logging() -> None:
    """Configure structlog processors once; merge_contextvars carries request_id from middleware."""
    app_env = os.getenv("APP_ENV", "development")

    shared_processors: list[structlog.types.Processor] = [
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if app_env == "production":
        processors = [*shared_processors, structlog.processors.JSONRenderer()]
    else:
        processors = [*shared_processors, structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
