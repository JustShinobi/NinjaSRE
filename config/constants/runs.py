"""Bounds for the durable trace, the live stream, and the scheduler.

Three concerns with one lifetime. A run is recorded, watched while it happens,
and — if it is a recurring one — started by a scheduler that had to decide it
was the only replica allowed to start it. Every ceiling below is named because
Article II says a bound at a call site is a defect: the payload cap that decides
what a trace can hold, the buffer that decides when a slow reader is dropped,
and the two semaphores that decide how much of a deployment one team may occupy.

The lease and claim bounds live in ``persistence`` beside the port that
implements them. What is here is what the scheduler layer decides for itself.
"""

from __future__ import annotations

from typing import Final

# --- Trace payloads ----------------------------------------------------------

#: Largest tool argument, tool result, or trace-event payload written to a
#: single record. Well under the JSONB bound the store enforces, because a
#: payload that only fails at the storage layer fails after the run has already
#: spent the time producing it.
MAX_TRACE_PAYLOAD_BYTES: Final[int] = 65_536

#: Key added beside a truncated value, holding what was removed and why. The
#: marker is a sibling rather than a suffix on the value so a reader parsing the
#: payload finds it without having to inspect strings.
TRUNCATION_MARKER_KEY: Final[str] = "_truncated"

#: What a truncated string ends with. Present in the value itself as well as in
#: the marker, because the value is what a human reads first and a silently cut
#: string is indistinguishable from a short one.
TRUNCATION_SUFFIX: Final[str] = " …[truncated]"

#: Longest single string kept inside a payload. A tool that returns a hundred
#: thousand log lines stores a reference and a summary; the cap is what makes
#: that a requirement rather than a suggestion.
MAX_TRACE_STRING_LENGTH: Final[int] = 8_192

#: Deepest nesting a recorded payload keeps. Below it the branch is replaced by
#: a marker: an arbitrarily nested structure is a way to spend the byte cap on
#: braces, and nothing legible lives twelve levels down.
MAX_TRACE_PAYLOAD_DEPTH: Final[int] = 12

#: Most entries kept from one sequence. Same reason as the depth bound, and the
#: marker records how many were dropped.
MAX_TRACE_SEQUENCE_ITEMS: Final[int] = 200

# --- What a run record carries beside its own columns ------------------------

#: Keys inside a run's metadata. They are named here rather than written at each
#: call site because the recorder writes them and the history reader filters on
#: them, and a typo in one of the two produces an empty result rather than an
#: error.
RUN_METADATA_TEAM: Final[str] = "team_node_id"
RUN_METADATA_PRINCIPAL: Final[str] = "principal_id"
RUN_METADATA_PARENT: Final[str] = "parent_run_id"
RUN_METADATA_SUBAGENT: Final[str] = "subagent"
RUN_METADATA_JOB: Final[str] = "job_id"
RUN_METADATA_INTERRUPTION: Final[str] = "interruption_reason"

#: Keys inside a turn's payload and usage. ``selection_rationale`` is the one a
#: reviewer reads to see *why* those capabilities were offered, which is the
#: half of a decision the call list alone does not record.
TURN_PAYLOAD_RATIONALE: Final[str] = "selection_rationale"
TURN_PAYLOAD_CAPABILITIES: Final[str] = "offered_capabilities"
TURN_USAGE_MODEL: Final[str] = "model"
TURN_USAGE_PROMPT_TOKENS: Final[str] = "prompt_tokens"
TURN_USAGE_COMPLETION_TOKENS: Final[str] = "completion_tokens"
TURN_USAGE_COST: Final[str] = "cost"
TURN_USAGE_DURATION_MS: Final[str] = "duration_ms"

#: What started a run. A scheduled run and an interactive one differ in this
#: and in their principal, and in nothing else — which is what lets one history
#: hold both.
TRIGGER_INTERACTIVE: Final[str] = "interactive"
TRIGGER_ALERT: Final[str] = "alert"
TRIGGER_SCHEDULE: Final[str] = "schedule"
TRIGGER_SUBAGENT: Final[str] = "subagent"

# --- Streaming ---------------------------------------------------------------

#: Events a subscriber may fall behind by before it is disconnected. A slow
#: reader that is never dropped is a memory leak with a client attached; the
#: dropped one reconnects with its cursor and misses nothing, which is the whole
#: reason the event log rather than the pub/sub is the source of truth.
MAX_STREAM_BUFFER_EVENTS: Final[int] = 512

#: Events one catch-up read pulls from the log. Bounded so a client reconnecting
#: to a long run streams its backlog instead of materialising it whole.
STREAM_CATCH_UP_PAGE_SIZE: Final[int] = 200

#: Channel a Postgres ``NOTIFY`` carries run events on, so replicas other than
#: the recording one can serve a live subscriber.
RUN_EVENT_CHANNEL: Final[str] = "ninjasre_run_events"

# --- Scheduling --------------------------------------------------------------

#: How often a worker renews the lease on a job it is executing. Comfortably
#: inside ``JOB_CLAIM_LEASE_SECONDS`` so an ordinary pause — a long capability
#: call, a garbage collection — does not look like a death.
SCHEDULER_HEARTBEAT_SECONDS: Final[float] = 60.0

#: Scheduled investigations one deployment runs at once. Above this they queue:
#: a scheduler that starts everything due at midnight is a scheduler that takes
#: the platform down at midnight.
SCHEDULER_GLOBAL_CONCURRENCY: Final[int] = 8

#: Scheduled investigations one team runs at once. Lower than the global bound
#: on purpose — one team's nightly sweep must not be able to occupy every slot
#: in the deployment.
SCHEDULER_TEAM_CONCURRENCY: Final[int] = 2

#: How long after its fire time a job may still start before the run is treated
#: as a misfire. Below this the system was merely busy; above it, it was down,
#: and the two deserve different policies.
SCHEDULER_MISFIRE_GRACE_SECONDS: Final[float] = 300.0

#: Fire times one ``run_all`` misfire recovery replays. A deployment down for a
#: week must not wake up and start two thousand investigations.
MAX_MISFIRE_CATCH_UP_RUNS: Final[int] = 10

#: How far ahead cron evaluation will search for the next fire time before
#: giving up. Four years covers every February 29th an expression can name; an
#: unbounded search is how an impossible expression becomes a hang.
MAX_CRON_LOOKAHEAD_DAYS: Final[int] = 1_500

#: Timezone a schedule with none configured is evaluated in. UTC rather than the
#: host's zone: a job that moved because a replica was scheduled onto a machine
#: in another region is a fault nobody can reproduce.
DEFAULT_SCHEDULE_TIMEZONE: Final[str] = "UTC"

#: Firings a cron preview returns. Two rather than one: "next Monday 08:00,
#: then the Monday after" is what actually catches a wrong field position, and
#: a second call to the same ``next_after`` the write path already runs is
#: close enough to free that there is no reason to show only the first.
SCHEDULE_PREVIEW_FIRING_COUNT: Final[int] = 2

# --- Run history -------------------------------------------------------------

#: Runs one history query returns. The store's own page bound is higher; this is
#: what a console asks for, and paging is by time range.
DEFAULT_RUN_HISTORY_PAGE_SIZE: Final[int] = 50


__all__ = [
    "DEFAULT_RUN_HISTORY_PAGE_SIZE",
    "DEFAULT_SCHEDULE_TIMEZONE",
    "MAX_CRON_LOOKAHEAD_DAYS",
    "MAX_MISFIRE_CATCH_UP_RUNS",
    "MAX_STREAM_BUFFER_EVENTS",
    "MAX_TRACE_PAYLOAD_BYTES",
    "MAX_TRACE_PAYLOAD_DEPTH",
    "MAX_TRACE_SEQUENCE_ITEMS",
    "MAX_TRACE_STRING_LENGTH",
    "RUN_EVENT_CHANNEL",
    "RUN_METADATA_INTERRUPTION",
    "RUN_METADATA_JOB",
    "RUN_METADATA_PARENT",
    "RUN_METADATA_PRINCIPAL",
    "RUN_METADATA_SUBAGENT",
    "RUN_METADATA_TEAM",
    "SCHEDULE_PREVIEW_FIRING_COUNT",
    "SCHEDULER_GLOBAL_CONCURRENCY",
    "SCHEDULER_HEARTBEAT_SECONDS",
    "SCHEDULER_MISFIRE_GRACE_SECONDS",
    "SCHEDULER_TEAM_CONCURRENCY",
    "STREAM_CATCH_UP_PAGE_SIZE",
    "TRIGGER_ALERT",
    "TRIGGER_INTERACTIVE",
    "TRIGGER_SCHEDULE",
    "TRIGGER_SUBAGENT",
    "TRUNCATION_MARKER_KEY",
    "TRUNCATION_SUFFIX",
    "TURN_PAYLOAD_CAPABILITIES",
    "TURN_PAYLOAD_RATIONALE",
    "TURN_USAGE_COMPLETION_TOKENS",
    "TURN_USAGE_COST",
    "TURN_USAGE_DURATION_MS",
    "TURN_USAGE_MODEL",
    "TURN_USAGE_PROMPT_TOKENS",
]
