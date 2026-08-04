"""Structured logging, configured once for the whole process (FR-015).

This is the only module in NinjaSRE that may call ``structlog.configure`` or
``logging.basicConfig``; ``tests/unit/platform/test_logging_is_configured_once.py``
asserts it. A module that configures its own logging wins or loses depending on
import order, which is the kind of bug that only appears in the deployment where
it matters.

Everywhere else::

    from platform.observability.logging import get_logger

    logger = get_logger(__name__)
    logger.info("evidence.collected", capability="grafana.query", entries=17)

The event name is a stable identifier and the context is keyword arguments, not
an interpolated sentence. That is what makes a log queryable, and it is the same
discipline Article I asks of the investigation itself: the structure carries the
meaning, and prose is not evidence.

Nothing written here is trusted with secrets. Every value bound for a log passes
the guardrail engine first (Article IV, clause 4).
"""

from __future__ import annotations

import logging
import os
import sys

import structlog

from config.constants.observability import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    LOG_FORMAT_CONSOLE,
    LOG_FORMAT_JSON,
    LOG_FORMATS,
    LOG_LEVELS,
    LOG_TIMESTAMP_FORMAT,
    NINJASRE_LOG_FORMAT_ENV,
    NINJASRE_LOG_LEVEL_ENV,
)

_configured = False


def resolve_log_level() -> str:
    """Return the configured level, falling back to the default when unset."""
    requested = os.environ.get(NINJASRE_LOG_LEVEL_ENV, "").strip().upper()
    return requested if requested in LOG_LEVELS else DEFAULT_LOG_LEVEL


def resolve_log_format() -> str:
    """Return the configured renderer.

    An interactive terminal gets the console renderer; anything else gets JSON,
    because a log that is being captured is a log that will be parsed.
    """
    requested = os.environ.get(NINJASRE_LOG_FORMAT_ENV, "").strip().lower()
    if requested in LOG_FORMATS:
        return requested
    return LOG_FORMAT_CONSOLE if sys.stderr.isatty() else DEFAULT_LOG_FORMAT


def _renderer(log_format: str) -> structlog.typing.Processor:
    """Return the final processor for ``log_format``."""
    if log_format == LOG_FORMAT_JSON:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())


def configure_logging(*, force: bool = False) -> None:
    """Configure structlog and the stdlib root logger for this process.

    Idempotent: repeated calls are ignored so an entry point can call it without
    knowing whether another already did. ``force`` re-applies it, which is what
    tests need when they change the environment.

    The stdlib root is configured too, so a third-party library's ``logging``
    output is rendered the same way rather than escaping in its own format.
    """
    global _configured

    if _configured and not force:
        return

    level = resolve_log_level()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level),
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt=LOG_TIMESTAMP_FORMAT, utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            _renderer(resolve_log_format()),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return the logger for ``name``, configuring the process on first use.

    ``name`` is the calling module's ``__name__``, so a log line says which
    module emitted it without anyone having to repeat that in the message.
    """
    configure_logging()
    return structlog.stdlib.get_logger(name)


__all__ = ["configure_logging", "get_logger", "resolve_log_format", "resolve_log_level"]
