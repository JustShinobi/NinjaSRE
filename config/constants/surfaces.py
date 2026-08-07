"""Surface identifiers and the ports each entry point listens on.

The five entry points. An investigation started from any of them produces the
same result and the same trace, so the identifier
is trace metadata — it records where a run came in, never what it is allowed to
do. Authorisation is RBAC's job (feature 014), not the surface's.

Ports are defaults. A deployment profile overrides them, and nothing binds a
port without reading the effective configuration first.
"""

from __future__ import annotations

from collections.abc import Mapping
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

# --- Chat streaming ------------------------------------------------------------

#: How often the one progress message a run posts is edited. A chat platform
#: punishes a message per event with rate limits and an unreadable thread, so a
#: run's progress is *one* message rewritten on this interval however many
#: events arrive in between.
CHAT_STREAM_EDIT_INTERVAL_SECONDS: Final[float] = 3.0

#: Edits one message may receive per minute, per platform. Below each vendor's
#: published ceiling on purpose: a bot sharing a workspace with an alerting
#: integration does not get the whole budget to itself.
CHAT_MAX_EDITS_PER_MINUTE: Final[Mapping[str, int]] = {
    CHAT_PLATFORM_SLACK: 18,
    CHAT_PLATFORM_MICROSOFT_TEAMS: 30,
    CHAT_PLATFORM_TELEGRAM: 18,
    CHAT_PLATFORM_DISCORD: 24,
}

#: The first wait after a platform reports a rate limit, and the ceiling the
#: doubling stops at. A platform that sends ``Retry-After`` overrides both — its
#: own number is the only one that is actually right.
CHAT_RATE_LIMIT_BACKOFF_SECONDS: Final[float] = 1.0
CHAT_RATE_LIMIT_MAX_BACKOFF_SECONDS: Final[float] = 30.0
CHAT_RATE_LIMIT_BACKOFF_FACTOR: Final[float] = 2.0

#: How many consecutive rate limits or transport failures a progress stream
#: absorbs before it stops editing and lets the run finish unwatched. The run
#: itself never fails on this — chat is a surface, not the runtime.
CHAT_MAX_DELIVERY_ATTEMPTS: Final[int] = 5

#: The event count a long investigation is validated against: streamed inside
#: every platform's edit ceiling, however many events it produced.
CHAT_STREAM_BENCHMARK_EVENTS: Final[int] = 200

# --- Chat message limits -------------------------------------------------------

#: The largest single message each platform accepts, in characters. A report
#: above this is split or attached, and never silently cut.
CHAT_MESSAGE_LIMITS: Final[Mapping[str, int]] = {
    CHAT_PLATFORM_SLACK: 3_000,
    CHAT_PLATFORM_MICROSOFT_TEAMS: 28_000,
    CHAT_PLATFORM_TELEGRAM: 4_096,
    CHAT_PLATFORM_DISCORD: 2_000,
}

#: Above this many chunks a report is attached as a file instead of split.
#: Fifteen messages is where a thread stops being readable, and an attachment
#: keeps the whole report in one addressable place.
CHAT_MAX_REPORT_CHUNKS: Final[int] = 15

#: The marker a split report carries so a reader can tell a part from the whole,
#: and can see that nothing is missing.
CHAT_CHUNK_CONTINUATION_MARKER: Final = "…"

# --- Chat thread history -------------------------------------------------------

#: How many earlier messages of a thread may inform an investigation, and the
#: total characters they may contribute. Thread history is data, never
#: instructions, and a bound is what stops a channel from becoming an unbounded
#: prompt.
CHAT_THREAD_HISTORY_LIMIT: Final[int] = 50
CHAT_THREAD_HISTORY_MAX_CHARS: Final[int] = 12_000

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

# --- Web console rendering budgets --------------------------------------------

#: The transcript length the console is required to stay responsive at. A real
#: investigation produces thousands of events; this is the number the benchmark
#: proves rather than the number anybody expects.
CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS: Final[int] = 10_000

#: How long rendering one transcript screen may take, whatever the transcript's
#: length. Windowed rendering makes this independent of the total, so a failure
#: here means the renderer started touching every event again.
CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS: Final[float] = 60.0

#: How much longer a ten-thousand-event transcript may take to render than a
#: hundred-event one. Windowing makes the honest answer "no longer at all"; the
#: allowance is for measurement noise, not for growth.
CONSOLE_TRANSCRIPT_SCALING_TOLERANCE: Final[float] = 3.0

#: The organisation size the tree has to stay navigable at (SC-008).
CONSOLE_ORG_TREE_BENCHMARK_NODES: Final[int] = 500

#: How long building a five-hundred-node organisation tree may take. Well inside
#: an interaction budget, and low enough that a quadratic tree builder fails
#: rather than merely being slow.
CONSOLE_ORG_TREE_BUDGET_MS: Final[float] = 50.0

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
    "CHAT_CHUNK_CONTINUATION_MARKER",
    "CHAT_MAX_DELIVERY_ATTEMPTS",
    "CHAT_MAX_EDITS_PER_MINUTE",
    "CHAT_MAX_REPORT_CHUNKS",
    "CHAT_MESSAGE_LIMITS",
    "CHAT_PLATFORMS",
    "CHAT_PLATFORM_DISCORD",
    "CHAT_PLATFORM_MICROSOFT_TEAMS",
    "CHAT_PLATFORM_SLACK",
    "CHAT_PLATFORM_TELEGRAM",
    "CHAT_RATE_LIMIT_BACKOFF_FACTOR",
    "CHAT_RATE_LIMIT_BACKOFF_SECONDS",
    "CHAT_RATE_LIMIT_MAX_BACKOFF_SECONDS",
    "CHAT_STREAM_BENCHMARK_EVENTS",
    "CHAT_STREAM_EDIT_INTERVAL_SECONDS",
    "CHAT_THREAD_HISTORY_LIMIT",
    "CHAT_THREAD_HISTORY_MAX_CHARS",
    "CLI_COMMAND_NAME",
    "COLUMNS_ENV",
    "CONSOLE_ORG_TREE_BENCHMARK_NODES",
    "CONSOLE_ORG_TREE_BUDGET_MS",
    "CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS",
    "CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS",
    "CONSOLE_TRANSCRIPT_SCALING_TOLERANCE",
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
