"""Structured logging setup.

`structlog` is configured to render human friendly output locally and JSON in
deployed environments so logs can be shipped to Loki/ELK without a parser.
The standard library `logging` module is routed through the same pipeline so
third party libraries (uvicorn, SQLAlchemy, celery) share one output format.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.types import Processor

from app.core.config import Settings, get_settings
from app.core.security import sanitize_log_values

_configured = False


def _sanitize_log_event(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Redact password/token/api_key fields from every log event."""
    sanitized = sanitize_log_values(dict(event_dict))
    event_dict.clear()
    event_dict.update(sanitized)
    return event_dict


def _build_processors(settings: Settings) -> list[Processor]:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _sanitize_log_event,
    ]
    if settings.LOG_FORMAT == "json":
        shared += [
            structlog.processors.format_exc_info,
            structlog.processors.EventRenamer("message"),
        ]
    else:
        shared += [structlog.dev.set_exc_info]
    return shared


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structlog + stdlib logging. Safe to call more than once."""
    global _configured
    settings = settings or get_settings()
    if _configured:
        return

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.LOG_FORMAT == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *_build_processors(settings),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_build_processors(settings),
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL)

    # uvicorn and celery install their own handlers; delegate them to the root logger.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # RequestContextMiddleware already logs one structured line per request, with
    # health probes demoted to debug. Keeping uvicorn's plain-text access log on
    # top of that would double every line and flood the output with probes.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger.bind(**initial_values) if initial_values else logger
