"""Surface identifiers and the ports each entry point listens on.

The five entry points. An investigation started from any of them produces the
same result and the same trace, so the identifier
is trace metadata — it records where a run came in, never what it is allowed to
do. Authorisation is RBAC's job (feature 014), not the surface's.

Ports are defaults. A deployment profile overrides them, and nothing binds a
port without reading the effective configuration first.
"""

from __future__ import annotations

from typing import Final

# --- Surface identifiers -----------------------------------------------------

SURFACE_CLI: Final = "cli"
SURFACE_REPL: Final = "repl"
SURFACE_REST_API: Final = "rest_api"
SURFACE_WEB_CONSOLE: Final = "web_console"
SURFACE_CHAT: Final = "chat"

SURFACE_IDENTIFIERS: Final[tuple[str, ...]] = (
    SURFACE_CLI,
    SURFACE_REPL,
    SURFACE_REST_API,
    SURFACE_WEB_CONSOLE,
    SURFACE_CHAT,
)

# --- Chat platforms ----------------------------------------------------------

CHAT_PLATFORM_SLACK: Final = "slack"
CHAT_PLATFORM_MICROSOFT_TEAMS: Final = "microsoft_teams"
CHAT_PLATFORM_TELEGRAM: Final = "telegram"
CHAT_PLATFORM_DISCORD: Final = "discord"

CHAT_PLATFORMS: Final[tuple[str, ...]] = (
    CHAT_PLATFORM_SLACK,
    CHAT_PLATFORM_MICROSOFT_TEAMS,
    CHAT_PLATFORM_TELEGRAM,
    CHAT_PLATFORM_DISCORD,
)

# --- Ports -------------------------------------------------------------------

NINJASRE_API_HOST_ENV: Final = "NINJASRE_API_HOST"
NINJASRE_API_PORT_ENV: Final = "NINJASRE_API_PORT"
NINJASRE_CONSOLE_PORT_ENV: Final = "NINJASRE_CONSOLE_PORT"
NINJASRE_PROXY_PORT_ENV: Final = "NINJASRE_PROXY_PORT"

#: Loopback by default. Binding to every interface is an operator decision, made
#: once, in a deployment profile — not a default that ships open.
DEFAULT_API_HOST: Final = "127.0.0.1"

DEFAULT_API_PORT: Final[int] = 8420
DEFAULT_CONSOLE_PORT: Final[int] = 8421
DEFAULT_CREDENTIAL_PROXY_PORT: Final[int] = 8422

# --- Streaming ---------------------------------------------------------------

#: Server-sent events carry live investigation progress. The keep-alive keeps
#: proxies from closing an idle stream during a long tool call.
SSE_KEEPALIVE_INTERVAL_SECONDS: Final[float] = 15.0

#: How long a disconnected client may reconnect and resume a run's event stream
#: from where it left off (feature 016).
SSE_REPLAY_WINDOW_SECONDS: Final[float] = 300.0

# --- CLI ---------------------------------------------------------------------

CLI_COMMAND_NAME: Final = "ninjasre"

NINJASRE_NO_COLOR_ENV: Final = "NINJASRE_NO_COLOR"
NINJASRE_OUTPUT_FORMAT_ENV: Final = "NINJASRE_OUTPUT_FORMAT"

OUTPUT_FORMAT_TEXT: Final = "text"
OUTPUT_FORMAT_JSON: Final = "json"

OUTPUT_FORMATS: Final[tuple[str, ...]] = (OUTPUT_FORMAT_TEXT, OUTPUT_FORMAT_JSON)


__all__ = [
    "CHAT_PLATFORMS",
    "CHAT_PLATFORM_DISCORD",
    "CHAT_PLATFORM_MICROSOFT_TEAMS",
    "CHAT_PLATFORM_SLACK",
    "CHAT_PLATFORM_TELEGRAM",
    "CLI_COMMAND_NAME",
    "DEFAULT_API_HOST",
    "DEFAULT_API_PORT",
    "DEFAULT_CONSOLE_PORT",
    "DEFAULT_CREDENTIAL_PROXY_PORT",
    "NINJASRE_API_HOST_ENV",
    "NINJASRE_API_PORT_ENV",
    "NINJASRE_CONSOLE_PORT_ENV",
    "NINJASRE_NO_COLOR_ENV",
    "NINJASRE_OUTPUT_FORMAT_ENV",
    "NINJASRE_PROXY_PORT_ENV",
    "OUTPUT_FORMATS",
    "OUTPUT_FORMAT_JSON",
    "OUTPUT_FORMAT_TEXT",
    "SSE_KEEPALIVE_INTERVAL_SECONDS",
    "SSE_REPLAY_WINDOW_SECONDS",
    "SURFACE_CHAT",
    "SURFACE_CLI",
    "SURFACE_IDENTIFIERS",
    "SURFACE_REPL",
    "SURFACE_REST_API",
    "SURFACE_WEB_CONSOLE",
]
