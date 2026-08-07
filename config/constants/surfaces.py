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

# --- REST API rate limiting ---------------------------------------------------

#: Requests one principal may make per window. Separate from the team limit
#: below because a single misbehaving token must not be able to spend a whole
#: team's share before anyone else's calls are affected.
API_RATE_LIMIT_WINDOW_SECONDS: Final[float] = 60.0
API_MAX_REQUESTS_PER_PRINCIPAL: Final[int] = 300
API_MAX_REQUESTS_PER_TEAM: Final[int] = 1_200

# --- Webhook ingestion ---------------------------------------------------------

#: Largest webhook body accepted before verification is even attempted. Above
#: this the payload is rejected with a named reason (FR-021) rather than read
#: into memory — an oversize body is refused cheaply, not parsed first.
WEBHOOK_MAX_PAYLOAD_BYTES: Final[int] = 1_048_576

#: Window a repeat alert is linked to an existing investigation rather than
#: starting a new one (FR-018). Long enough to cover a flapping check's retries,
#: short enough that a genuinely new incident an hour later is not swallowed.
ALERT_DEDUP_WINDOW_SECONDS: Final[float] = 600.0

#: Inbound webhooks accepted per source per team, per window, before ingestion
#: sheds load (FR-020). An alert storm past this is recorded as shed, never
#: silently dropped.
WEBHOOK_RATE_LIMIT_WINDOW_SECONDS: Final[float] = 60.0
WEBHOOK_MAX_REQUESTS_PER_TEAM: Final[int] = 500

# --- Graceful shutdown ---------------------------------------------------------

#: How long shutdown waits for investigations already running to reach a safe
#: point before asking them to stop there directly (FR-025). Long enough for a
#: tool call in flight to finish; not so long that a deploy hangs on one slow
#: run.
GATEWAY_SHUTDOWN_DRAIN_SECONDS: Final[float] = 30.0

# --- CLI ---------------------------------------------------------------------

CLI_COMMAND_NAME: Final = "ninjasre"

NINJASRE_NO_COLOR_ENV: Final = "NINJASRE_NO_COLOR"
NINJASRE_OUTPUT_FORMAT_ENV: Final = "NINJASRE_OUTPUT_FORMAT"

OUTPUT_FORMAT_TEXT: Final = "text"
OUTPUT_FORMAT_JSON: Final = "json"

OUTPUT_FORMATS: Final[tuple[str, ...]] = (OUTPUT_FORMAT_TEXT, OUTPUT_FORMAT_JSON)

#: Which deployment a command talks to. Local starts what it needs in process;
#: remote makes the CLI a thin client over the REST API.
NINJASRE_ENDPOINT_ENV: Final = "NINJASRE_ENDPOINT"

TRANSPORT_LOCAL: Final = "local"
TRANSPORT_REMOTE: Final = "remote"

# --- Exit codes --------------------------------------------------------------

#: The exit-code contract. A script branching on these is the reason they are
#: named constants and the reason nothing may reuse one for a second meaning:
#: an operator's runbook that treats 3 as "fix your configuration" has to keep
#: being right after a release that added a failure mode.
#:
#: 2 is absent on purpose. The CLI framework exits 2 for a usage error before
#: any command body runs, and claiming the number for something else would make
#: one code mean two things depending on how far the process got.
EXIT_OK: Final[int] = 0
EXIT_FAILED: Final[int] = 1
EXIT_USAGE: Final[int] = 2
EXIT_CONFIGURATION: Final[int] = 3
EXIT_NOT_FOUND: Final[int] = 4
EXIT_DENIED: Final[int] = 5
EXIT_UNAVAILABLE: Final[int] = 6
EXIT_NEEDS_APPROVAL: Final[int] = 7

#: Interrupted. 128 + SIGINT, which is what a shell reports for a process a
#: user stopped, and what every wrapper script already knows how to read.
EXIT_INTERRUPTED: Final[int] = 130

# --- JSON output -------------------------------------------------------------

#: Every ``--json`` document is one envelope with these five keys, so a script
#: reads the same shape from every command and a schema change is visible in
#: the identifier rather than only in the payload.
JSON_ENVELOPE_KEYS: Final[tuple[str, ...]] = ("schema", "command", "ok", "data", "errors")

#: The prefix every published output schema identifier carries.
JSON_SCHEMA_PREFIX: Final = "ninjasre.cli"

#: Bumped when an envelope or a payload shape changes in a way a reader would
#: notice. Carried in every document so a script can refuse a version it does
#: not understand rather than misreading it.
JSON_SCHEMA_VERSION: Final = "v1"

# --- Presentation ------------------------------------------------------------

#: What a terminal is assumed to be when nothing reports a size — a pipe, a CI
#: log, a serial console. Eighty is the width every one of those is readable at.
DEFAULT_TERMINAL_WIDTH: Final[int] = 80

#: Below this, tables stop being tables: columns are printed as labelled lines
#: instead, because a four-column table wrapped into a 40-column window is less
#: readable than the same values one per row.
MINIMUM_TABLE_WIDTH: Final[int] = 60

#: Honoured whatever its value, per the no-color.org convention.
NO_COLOR_ENV: Final = "NO_COLOR"

#: Set by a terminal that reports colour support explicitly.
FORCE_COLOR_ENV: Final = "FORCE_COLOR"

TERM_ENV: Final = "TERM"

#: A terminal's own report of its width. Read rather than probed when it is
#: set, because a multiplexer that resized a pane sets this and the ioctl
#: answers for the outer window.
COLUMNS_ENV: Final = "COLUMNS"

#: The value a terminal reports when it has no capabilities at all.
TERM_DUMB: Final = "dumb"

# --- REPL --------------------------------------------------------------------

#: The one character that makes a line a directive rather than something for the
#: agent. A literal prefix and nothing else: no regex, no keyword matching, no
#: "looks like a command" heuristic. ``surfaces/repl/AGENTS.md`` records why.
SLASH_COMMAND_PREFIX: Final = "/"

#: How many lines of REPL input are kept across sessions.
REPL_HISTORY_LIMIT: Final[int] = 1_000

REPL_HISTORY_FILE_NAME: Final = "repl-history"

#: How long the REPL waits for a cancelled run to reach its next safe point
#: before reporting that it did not stop. Long enough for a tool call to
#: unwind, short enough that a second Ctrl+C is not the operator's first idea.
REPL_CANCEL_GRACE_SECONDS: Final[float] = 10.0


__all__ = [
    "ALERT_DEDUP_WINDOW_SECONDS",
    "API_MAX_REQUESTS_PER_PRINCIPAL",
    "API_MAX_REQUESTS_PER_TEAM",
    "API_RATE_LIMIT_WINDOW_SECONDS",
    "CHAT_PLATFORMS",
    "CHAT_PLATFORM_DISCORD",
    "CHAT_PLATFORM_MICROSOFT_TEAMS",
    "CHAT_PLATFORM_SLACK",
    "CHAT_PLATFORM_TELEGRAM",
    "CLI_COMMAND_NAME",
    "COLUMNS_ENV",
    "DEFAULT_API_HOST",
    "DEFAULT_API_PORT",
    "DEFAULT_CONSOLE_PORT",
    "DEFAULT_CREDENTIAL_PROXY_PORT",
    "DEFAULT_TERMINAL_WIDTH",
    "EXIT_CONFIGURATION",
    "EXIT_DENIED",
    "EXIT_FAILED",
    "EXIT_INTERRUPTED",
    "EXIT_NEEDS_APPROVAL",
    "EXIT_NOT_FOUND",
    "EXIT_OK",
    "EXIT_UNAVAILABLE",
    "EXIT_USAGE",
    "FORCE_COLOR_ENV",
    "GATEWAY_SHUTDOWN_DRAIN_SECONDS",
    "JSON_ENVELOPE_KEYS",
    "JSON_SCHEMA_PREFIX",
    "JSON_SCHEMA_VERSION",
    "MINIMUM_TABLE_WIDTH",
    "NINJASRE_API_HOST_ENV",
    "NINJASRE_API_PORT_ENV",
    "NINJASRE_CONSOLE_PORT_ENV",
    "NINJASRE_ENDPOINT_ENV",
    "NINJASRE_NO_COLOR_ENV",
    "NINJASRE_OUTPUT_FORMAT_ENV",
    "NINJASRE_PROXY_PORT_ENV",
    "NO_COLOR_ENV",
    "OUTPUT_FORMATS",
    "OUTPUT_FORMAT_JSON",
    "OUTPUT_FORMAT_TEXT",
    "REPL_CANCEL_GRACE_SECONDS",
    "REPL_HISTORY_FILE_NAME",
    "REPL_HISTORY_LIMIT",
    "SLASH_COMMAND_PREFIX",
    "SSE_KEEPALIVE_INTERVAL_SECONDS",
    "SSE_REPLAY_WINDOW_SECONDS",
    "SURFACE_CHAT",
    "SURFACE_CLI",
    "SURFACE_IDENTIFIERS",
    "SURFACE_REPL",
    "SURFACE_REST_API",
    "SURFACE_WEB_CONSOLE",
    "TERM_DUMB",
    "TERM_ENV",
    "TRANSPORT_LOCAL",
    "TRANSPORT_REMOTE",
    "WEBHOOK_MAX_PAYLOAD_BYTES",
    "WEBHOOK_MAX_REQUESTS_PER_TEAM",
    "WEBHOOK_RATE_LIMIT_WINDOW_SECONDS",
]
