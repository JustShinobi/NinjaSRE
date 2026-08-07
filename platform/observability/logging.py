"""Structured logging, configured once for the whole process.

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

**Nothing written here is trusted with secrets.** Every value bound for a log
passes the guardrail engine on its way out, as the last processor before the
renderer. That placement is the point: a call site cannot opt out, and it does
not have to know what was in the vendor error message it was handed.

**One conversation, one identifier.** ``correlated`` binds the correlation
identifier into the context, and every line emitted inside it carries it —
including from a module three layers down that never heard of the investigation.

**Per-module levels are re-read on demand.** Turning one subsystem up at 03:00
should not mean restarting the subsystem that is misbehaving.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from contextlib import contextmanager
from typing import Any, TextIO

import structlog

from config.constants.observability import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    LOG_CORRELATION_FIELD,
    LOG_FORMAT_CONSOLE,
    LOG_FORMAT_JSON,
    LOG_FORMATS,
    LOG_GUARDRAIL_FIELD,
    LOG_LEVELS,
    LOG_TIMESTAMP_FORMAT,
    MAX_LOG_VALUE_CHARS,
    MODULE_LEVEL_ASSIGNMENT,
    MODULE_LEVEL_SEPARATOR,
    NINJASRE_LOG_FORMAT_ENV,
    NINJASRE_LOG_LEVEL_ENV,
    NINJASRE_LOG_MODULE_LEVELS_ENV,
)

_configured = False

#: Marks a value the emission scan shortened, so a reader knows the line was cut
#: rather than that the vendor said exactly this much.
_TRUNCATION_MARKER = "… truncated"

#: The guardrail engine, built on first use rather than at import. This module
#: is imported by ``platform.guardrails`` itself, so an import-time construction
#: would be a cycle; and the engine loads an operator-editable ruleset, which is
#: not work an import should do.
_ENGINE: Any = None

#: Which modules have had a level applied, so a reload can clear the ones the
#: operator dropped from the setting rather than leaving them raised forever.
_MODULE_LEVELS: dict[str, str] = {}


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


# -- guardrail filtering at emission ------------------------------------------


def _engine() -> Any:
    """Return the shared guardrail engine, built on first use."""
    global _ENGINE
    if _ENGINE is None:
        from platform.guardrails.engine import GuardrailEngine

        _ENGINE = GuardrailEngine()
    return _ENGINE


def _scan(value: str, fired: dict[str, None]) -> str:
    """Return ``value`` with every match redacted, recording which rules fired."""
    result = _engine().scan(value)
    for rule in result.rules_fired:
        fired.setdefault(rule, None)
    text = str(result.text)
    if len(text) > MAX_LOG_VALUE_CHARS:
        return text[:MAX_LOG_VALUE_CHARS] + _TRUNCATION_MARKER
    return text


def _filtered(value: Any, fired: dict[str, None]) -> Any:
    """Return ``value`` with every string inside it scanned.

    Containers are walked rather than stringified, so a redacted mapping is
    still a mapping when the renderer reaches it. Anything that refuses to
    render is left alone: a log processor is not a place to raise, and an
    object whose ``__str__`` throws is the renderer's problem, not the
    guardrail's.
    """
    if isinstance(value, str):
        return _scan(value, fired)
    if isinstance(value, Mapping):
        return {key: _filtered(item, fired) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_filtered(item, fired) for item in value]
    if isinstance(value, bool | int | float) or value is None:
        return value
    try:
        return _scan(str(value), fired)
    except Exception:  # noqa: BLE001 — a log line must not fail on a bad __str__
        return value


def guardrail_processor(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Return ``event_dict`` with every value passed through the guardrail engine.

    The first two arguments are structlog's processor signature — the logger and
    the level's method name — and this filter decides from neither. Keeping them
    is what makes it a processor.

    The rules that fired are recorded on the line, and only when some did. A
    field present on every line would tell a reader nothing about any of them,
    and its absence is what makes a redaction findable.
    """
    fired: dict[str, None] = {}
    scanned = {key: _filtered(value, fired) for key, value in event_dict.items()}
    if fired:
        scanned[LOG_GUARDRAIL_FIELD] = list(fired)
    return scanned


# -- the correlation identifier -----------------------------------------------


def bind_correlation_id(correlation_id: str) -> None:
    """Bind ``correlation_id`` onto every line this context emits from now on."""
    structlog.contextvars.bind_contextvars(**{LOG_CORRELATION_FIELD: correlation_id})


def clear_correlation_id() -> None:
    """Remove the correlation identifier from this context."""
    structlog.contextvars.unbind_contextvars(LOG_CORRELATION_FIELD)


def current_correlation_id() -> str:
    """Return the identifier bound here, or an empty string when there is none."""
    bound = structlog.contextvars.get_contextvars().get(LOG_CORRELATION_FIELD, "")
    return str(bound)


@contextmanager
def correlated(correlation_id: str) -> Iterator[None]:
    """Bind ``correlation_id`` for the duration of the block, then put back what was there.

    Restoring rather than clearing, because a sub-investigation nested inside
    another must not silently orphan the outer one's remaining log lines.
    """
    previous = current_correlation_id()
    bind_correlation_id(correlation_id)
    try:
        yield
    finally:
        if previous:
            bind_correlation_id(previous)
        else:
            clear_correlation_id()


# -- per-module levels ---------------------------------------------------------


def set_module_level(module: str, level: str) -> None:
    """Raise or lower one module's log level, effective immediately.

    Raises:
        ValueError: ``level`` is not one of the levels this deployment knows.
            Silently ignoring it would leave an operator believing they had
            turned a subsystem up.
    """
    normalised = level.strip().upper()
    if normalised not in LOG_LEVELS:
        raise ValueError(
            f"{level!r} is not a log level; one of {', '.join(LOG_LEVELS)} was expected"
        )
    logging.getLogger(module).setLevel(getattr(logging, normalised))
    _MODULE_LEVELS[module] = normalised


def module_levels() -> dict[str, str]:
    """Return the per-module levels currently applied."""
    return dict(_MODULE_LEVELS)


def reload_module_levels(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Re-read the per-module levels from the environment and apply them.

    Returns what is now in force. A module that was raised and has since been
    dropped from the setting goes back to inheriting, which is what makes this
    a reload rather than an accumulation.

    A malformed pair is skipped rather than fatal: a typo in one entry must not
    silence the entry beside it, and this is a call an operator makes while
    something is already going wrong.
    """
    source = os.environ if environ is None else environ
    raw = source.get(NINJASRE_LOG_MODULE_LEVELS_ENV, "")

    requested: dict[str, str] = {}
    for pair in raw.split(MODULE_LEVEL_SEPARATOR):
        module, separator, level = pair.partition(MODULE_LEVEL_ASSIGNMENT)
        if not separator:
            continue
        module, level = module.strip(), level.strip().upper()
        if module and level in LOG_LEVELS:
            requested[module] = level

    for module in set(_MODULE_LEVELS) - set(requested):
        logging.getLogger(module).setLevel(logging.NOTSET)
        _MODULE_LEVELS.pop(module, None)
    for module, level in requested.items():
        set_module_level(module, level)

    return dict(sorted(_MODULE_LEVELS.items()))


# -- configuration -------------------------------------------------------------


def configure_logging(
    *,
    force: bool = False,
    log_format: str = "",
    stream: TextIO | None = None,
) -> None:
    """Configure structlog and the stdlib root logger for this process.

    Idempotent: repeated calls are ignored so an entry point can call it without
    knowing whether another already did. ``force`` re-applies it, which is what
    tests need when they change the environment.

    The stdlib root is configured too, so a third-party library's ``logging``
    output is rendered the same way rather than escaping in its own format.

    The guardrail scan sits last before the renderer. Anything a later processor
    added would otherwise leave unfiltered, and "last" is the only position that
    needs no argument about what runs after it.
    """
    global _configured

    if _configured and not force:
        return

    level = resolve_log_level()

    logging.basicConfig(
        format="%(message)s",
        stream=stream or sys.stderr,
        level=getattr(logging, level),
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt=LOG_TIMESTAMP_FORMAT, utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            guardrail_processor,
            _renderer(log_format or resolve_log_format()),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    reload_module_levels()
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return the logger for ``name``, configuring the process on first use.

    ``name`` is the calling module's ``__name__``, so a log line says which
    module emitted it without anyone having to repeat that in the message.
    """
    configure_logging()
    return structlog.stdlib.get_logger(name)


__all__ = [
    "bind_correlation_id",
    "clear_correlation_id",
    "configure_logging",
    "correlated",
    "current_correlation_id",
    "get_logger",
    "guardrail_processor",
    "module_levels",
    "reload_module_levels",
    "resolve_log_format",
    "resolve_log_level",
    "set_module_level",
]
