"""Logging configuration names and defaults.

Structured logging is configured exactly once, in
``platform/observability/logging.py`` (FR-015). No module configures its own.
These are the knobs that configuration reads.

OpenTelemetry, when it arrives, is opt-in and points at a collector the operator
names, and nothing here phones home. This module stops at logging.
"""

from __future__ import annotations

from typing import Final

NINJASRE_LOG_LEVEL_ENV: Final = "NINJASRE_LOG_LEVEL"
NINJASRE_LOG_FORMAT_ENV: Final = "NINJASRE_LOG_FORMAT"

DEFAULT_LOG_LEVEL: Final = "INFO"

LOG_LEVELS: Final[tuple[str, ...]] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

#: One JSON object per line, for a log shipper.
LOG_FORMAT_JSON: Final = "json"

#: Aligned, coloured key-value pairs, for a human at a terminal.
LOG_FORMAT_CONSOLE: Final = "console"

LOG_FORMATS: Final[tuple[str, ...]] = (LOG_FORMAT_JSON, LOG_FORMAT_CONSOLE)

#: Chosen when the operator names no format. A terminal gets the console
#: renderer and anything else gets JSON, because a log that is being captured is
#: a log that will be parsed.
DEFAULT_LOG_FORMAT: Final = LOG_FORMAT_JSON

#: Timestamps are ISO-8601 in UTC. An incident is reconstructed from logs
#: written in several timezones, and local time makes that guesswork.
LOG_TIMESTAMP_FORMAT: Final = "iso"


__all__ = [
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "LOG_FORMATS",
    "LOG_FORMAT_CONSOLE",
    "LOG_FORMAT_JSON",
    "LOG_LEVELS",
    "LOG_TIMESTAMP_FORMAT",
    "NINJASRE_LOG_FORMAT_ENV",
    "NINJASRE_LOG_LEVEL_ENV",
]
