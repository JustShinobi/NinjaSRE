"""Where a finished investigation goes, and what bounds getting somebody's attention.

Two related domains and one tier, because they share every bound that matters.
A report is delivered to a destination; a notification tells a human it is
there. The size a destination accepts, the number of times a failure is retried,
how long the same subject stays quiet, and how long an unaddressed item waits
before it escalates are all numbers an operator tunes together, so they are
named together.

Every window here is a *default*. A team's own configuration narrows it through
the config service; nothing widens it, because the ceilings are what stop a
misconfigured team from becoming the deployment's paging load.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

# --- Destination classes -------------------------------------------------------

#: The five rendering shapes. Thirteen destinations, five formatters: the
#: marginal cost of the fourteenth destination is a row in the table below
#: rather than a module, and that is the only reason thirteen is affordable.
DESTINATION_CLASS_CHAT: Final = "chat"
DESTINATION_CLASS_TICKET: Final = "ticket"
DESTINATION_CLASS_DOCUMENT: Final = "document"
DESTINATION_CLASS_MARKDOWN: Final = "markdown"
DESTINATION_CLASS_EMAIL: Final = "email"

DESTINATION_CLASSES: Final[tuple[str, ...]] = (
    DESTINATION_CLASS_CHAT,
    DESTINATION_CLASS_TICKET,
    DESTINATION_CLASS_DOCUMENT,
    DESTINATION_CLASS_MARKDOWN,
    DESTINATION_CLASS_EMAIL,
)

# --- The thirteen destinations -------------------------------------------------

DESTINATION_SLACK: Final = "slack"
DESTINATION_MICROSOFT_TEAMS: Final = "microsoft_teams"
DESTINATION_TELEGRAM: Final = "telegram"
DESTINATION_DISCORD: Final = "discord"
DESTINATION_JIRA: Final = "jira"
DESTINATION_GITHUB: Final = "github"
DESTINATION_GITLAB: Final = "gitlab"
DESTINATION_CONFLUENCE: Final = "confluence"
DESTINATION_NOTION: Final = "notion"
DESTINATION_GOOGLE_DOCS: Final = "google_docs"
DESTINATION_PAGERDUTY: Final = "pagerduty"
DESTINATION_LOCAL_MARKDOWN: Final = "local_markdown"
DESTINATION_EMAIL: Final = "email"

#: Which formatter renders each destination. Closed on purpose: a destination
#: nobody classified would fall to whichever branch was written first, and the
#: symptom is a postmortem page posted as a chat message.
DESTINATION_CLASS_OF: Final[Mapping[str, str]] = {
    DESTINATION_SLACK: DESTINATION_CLASS_CHAT,
    DESTINATION_MICROSOFT_TEAMS: DESTINATION_CLASS_CHAT,
    DESTINATION_TELEGRAM: DESTINATION_CLASS_CHAT,
    DESTINATION_DISCORD: DESTINATION_CLASS_CHAT,
    DESTINATION_JIRA: DESTINATION_CLASS_TICKET,
    DESTINATION_GITHUB: DESTINATION_CLASS_TICKET,
    DESTINATION_GITLAB: DESTINATION_CLASS_TICKET,
    DESTINATION_PAGERDUTY: DESTINATION_CLASS_TICKET,
    DESTINATION_CONFLUENCE: DESTINATION_CLASS_DOCUMENT,
    DESTINATION_NOTION: DESTINATION_CLASS_DOCUMENT,
    DESTINATION_GOOGLE_DOCS: DESTINATION_CLASS_DOCUMENT,
    DESTINATION_LOCAL_MARKDOWN: DESTINATION_CLASS_MARKDOWN,
    DESTINATION_EMAIL: DESTINATION_CLASS_EMAIL,
}

REPORT_DESTINATIONS: Final[tuple[str, ...]] = tuple(DESTINATION_CLASS_OF)

# --- Size limits ---------------------------------------------------------------

#: The largest body each destination accepts, in characters. A report above its
#: destination's number is *summarised with a link*, never cut: a truncated
#: report reads exactly like a short one, so the reader never learns that the
#: section answering their question was the part that did not fit.
DESTINATION_SIZE_LIMITS: Final[Mapping[str, int]] = {
    DESTINATION_SLACK: 3_000,
    DESTINATION_MICROSOFT_TEAMS: 28_000,
    DESTINATION_TELEGRAM: 4_096,
    DESTINATION_DISCORD: 2_000,
    DESTINATION_JIRA: 32_767,
    DESTINATION_GITHUB: 65_536,
    DESTINATION_GITLAB: 1_000_000,
    DESTINATION_PAGERDUTY: 1_024,
    DESTINATION_CONFLUENCE: 100_000,
    DESTINATION_NOTION: 100_000,
    DESTINATION_GOOGLE_DOCS: 100_000,
    DESTINATION_LOCAL_MARKDOWN: 1_000_000,
    DESTINATION_EMAIL: 100_000,
}

#: What a summarised report is allowed to spend before the link takes over,
#: expressed as a share of the destination's limit. Below 1.0 so the sentence
#: pointing at the full version is never itself the thing that does not fit.
REPORT_SUMMARY_BUDGET_RATIO: Final[float] = 0.8

#: The sentence a summarised delivery carries, so a reader knows there is more
#: and where it is. Never omitted — a summary that does not say it is one is
#: indistinguishable from a report that had nothing else to say.
REPORT_SUMMARY_NOTICE: Final = "This is a summary. The full report is at"

# --- Delivery ------------------------------------------------------------------

#: Attempts per destination before delivery is recorded as failed. Each attempt
#: carries the same idempotency key, so a destination that took the first one
#: and failed to answer does not receive a second copy.
REPORT_MAX_DELIVERY_ATTEMPTS: Final[int] = 4

#: The first wait after a transient failure, the factor it grows by, and the
#: ceiling it stops at.
REPORT_DELIVERY_BACKOFF_SECONDS: Final[float] = 1.0
REPORT_DELIVERY_BACKOFF_FACTOR: Final[float] = 2.0
REPORT_DELIVERY_MAX_BACKOFF_SECONDS: Final[float] = 30.0

#: Consecutive failed deliveries after which a destination is marked unhealthy
#: and surfaced to the operator. Consecutive rather than total: a destination
#: that failed twice last month and has worked since is working.
DESTINATION_UNHEALTHY_AFTER_FAILURES: Final[int] = 3

#: How long a destination stays marked unhealthy before delivery is attempted
#: again. Long enough that a vendor outage is not retried at full rate, short
#: enough that a rotated token starts working without an operator noticing.
DESTINATION_UNHEALTHY_COOLDOWN_SECONDS: Final[float] = 900.0

# --- Notification sinks ---------------------------------------------------------

SINK_PUSHOVER: Final = "pushover"
SINK_EMAIL: Final = "email"
SINK_WEBHOOK: Final = "webhook"
SINK_PAGERDUTY: Final = "pagerduty"
SINK_CHAT: Final = "chat"

NOTIFICATION_SINKS: Final[tuple[str, ...]] = (
    SINK_PUSHOVER,
    SINK_EMAIL,
    SINK_WEBHOOK,
    SINK_PAGERDUTY,
    SINK_CHAT,
)

#: The sinks that wake somebody. Quiet hours divert away from these; a critical
#: outcome is what overrides the diversion.
PAGING_SINKS: Final[tuple[str, ...]] = (SINK_PAGERDUTY, SINK_PUSHOVER)

# --- Pushover -------------------------------------------------------------------

#: Pushover's own priority scale, named rather than written as integers at the
#: call site. ``EMERGENCY`` repeats until acknowledged, which is why nothing
#: below a critical outcome may reach it.
PUSHOVER_PRIORITY_LOWEST: Final[int] = -2
PUSHOVER_PRIORITY_LOW: Final[int] = -1
PUSHOVER_PRIORITY_NORMAL: Final[int] = 0
PUSHOVER_PRIORITY_HIGH: Final[int] = 1
PUSHOVER_PRIORITY_EMERGENCY: Final[int] = 2

#: The vendor's published maxima. A title or message above them is refused by
#: the API, so the sink summarises to fit rather than discovering it at 03:00.
PUSHOVER_MAX_TITLE_CHARS: Final[int] = 250
PUSHOVER_MAX_MESSAGE_CHARS: Final[int] = 1_024
PUSHOVER_MAX_URL_CHARS: Final[int] = 512

#: The sound a paging notification uses, and the one everything else uses. Named
#: here because "which notification is worth the loud sound" is a policy
#: question, not a per-call decision.
PUSHOVER_SOUND_PAGING: Final = "persistent"
PUSHOVER_SOUND_DEFAULT: Final = "pushover"

# --- Severity and outcome -------------------------------------------------------

SEVERITY_CRITICAL: Final = "critical"
SEVERITY_HIGH: Final = "high"
SEVERITY_MEDIUM: Final = "medium"
SEVERITY_LOW: Final = "low"
SEVERITY_NOISE: Final = "noise"

#: Ordered most severe first, so "at least high" is a comparison rather than a
#: list somebody forgets to extend.
NOTIFICATION_SEVERITIES: Final[tuple[str, ...]] = (
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    SEVERITY_LOW,
    SEVERITY_NOISE,
)

# --- Cooldown, rate limits, quiet hours ------------------------------------------

#: How long the same subject stays quiet after a notification about it. Fifteen
#: minutes is roughly how long it takes to look at something, which is the point:
#: the second page adds nothing while the first is still being worked.
NOTIFICATION_COOLDOWN_SECONDS: Final[float] = 900.0

#: A critical outcome's own, shorter window. It is not zero — a flapping check
#: must not page ten times a minute — and it is short enough that a genuinely
#: worsening incident is not silenced.
CRITICAL_NOTIFICATION_COOLDOWN_SECONDS: Final[float] = 300.0

#: How many suppressions are retained per team so an operator can answer "why
#: wasn't I told". Bounded, because the answer is only ever wanted about the
#: recent past and an unbounded list is a leak driven by the noisiest team.
MAX_RETAINED_SUPPRESSIONS: Final[int] = 500

#: Notifications one team may be sent per window, across every sink. The limit
#: is per team rather than per sink: a human's attention is the scarce resource,
#: and it is not five times less scarce because five sinks are configured.
NOTIFICATION_RATE_LIMIT_WINDOW_SECONDS: Final[float] = 3_600.0
MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW: Final[int] = 20

#: The quiet-hours default, in the team's own timezone: 22:00 to 07:00. A
#: non-critical notification inside the window is diverted to a non-paging sink
#: rather than dropped — it is still there in the morning.
QUIET_HOURS_START_HOUR: Final[int] = 22
QUIET_HOURS_END_HOUR: Final[int] = 7

# --- Escalation -----------------------------------------------------------------

#: How long an attention item may sit unaddressed before it escalates. Ten
#: minutes: long enough that somebody already looking is not escalated past,
#: short enough that an approval nobody saw does not stall an incident.
ESCALATION_DELAY_SECONDS: Final[float] = 600.0

#: How many times one item escalates before it stops. An escalation that repeats
#: forever is a notification the recipient learns to filter.
MAX_ESCALATION_ROUNDS: Final[int] = 2

# --- Audience -------------------------------------------------------------------

#: What a sink's readership is, which decides two separate things: whether
#: masked identifiers are restored, and whether evidence bodies may appear at
#: all. ``private`` is the incident channel whose membership the operator
#: controls; ``team`` is a wider internal audience; ``public`` is a status page.
AUDIENCE_PRIVATE: Final = "private"
AUDIENCE_TEAM: Final = "team"
AUDIENCE_PUBLIC: Final = "public"

NOTIFICATION_AUDIENCES: Final[tuple[str, ...]] = (
    AUDIENCE_PRIVATE,
    AUDIENCE_TEAM,
    AUDIENCE_PUBLIC,
)

#: The only audience masked identifiers are put back for. Everything else reads
#: the token, which is meaningless without the run's mapping — and that is
#: exactly what makes leaving it there the right answer.
IDENTIFIER_AUTHORISED_AUDIENCES: Final[tuple[str, ...]] = (AUDIENCE_PRIVATE,)

# --- Trace and record keys --------------------------------------------------------

#: What a delivery record's payload is keyed on in the run trace. Named, because
#: a console reading the trace and the dispatcher writing it are two places that
#: have to agree.
DELIVERY_RECORD_DESTINATION: Final = "destination"
DELIVERY_RECORD_STATUS: Final = "status"
DELIVERY_RECORD_ATTEMPTS: Final = "attempts"
DELIVERY_RECORD_REASON: Final = "reason"
DELIVERY_RECORD_REFERENCE: Final = "reference"
DELIVERY_RECORD_SUMMARISED: Final = "summarised"

NOTIFICATION_RECORD_SINK: Final = "sink"
NOTIFICATION_RECORD_SUBJECT: Final = "subject"
NOTIFICATION_RECORD_SEVERITY: Final = "severity"
NOTIFICATION_RECORD_DECISION: Final = "decision"
NOTIFICATION_RECORD_REASON: Final = "reason"


__all__ = [
    "AUDIENCE_PRIVATE",
    "AUDIENCE_PUBLIC",
    "AUDIENCE_TEAM",
    "CRITICAL_NOTIFICATION_COOLDOWN_SECONDS",
    "DELIVERY_RECORD_ATTEMPTS",
    "DELIVERY_RECORD_DESTINATION",
    "DELIVERY_RECORD_REASON",
    "DELIVERY_RECORD_REFERENCE",
    "DELIVERY_RECORD_STATUS",
    "DELIVERY_RECORD_SUMMARISED",
    "DESTINATION_CLASSES",
    "DESTINATION_CLASS_CHAT",
    "DESTINATION_CLASS_DOCUMENT",
    "DESTINATION_CLASS_EMAIL",
    "DESTINATION_CLASS_MARKDOWN",
    "DESTINATION_CLASS_OF",
    "DESTINATION_CLASS_TICKET",
    "DESTINATION_CONFLUENCE",
    "DESTINATION_DISCORD",
    "DESTINATION_EMAIL",
    "DESTINATION_GITHUB",
    "DESTINATION_GITLAB",
    "DESTINATION_GOOGLE_DOCS",
    "DESTINATION_JIRA",
    "DESTINATION_LOCAL_MARKDOWN",
    "DESTINATION_MICROSOFT_TEAMS",
    "DESTINATION_NOTION",
    "DESTINATION_PAGERDUTY",
    "DESTINATION_SIZE_LIMITS",
    "DESTINATION_SLACK",
    "DESTINATION_TELEGRAM",
    "DESTINATION_UNHEALTHY_AFTER_FAILURES",
    "DESTINATION_UNHEALTHY_COOLDOWN_SECONDS",
    "ESCALATION_DELAY_SECONDS",
    "IDENTIFIER_AUTHORISED_AUDIENCES",
    "MAX_ESCALATION_ROUNDS",
    "MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW",
    "MAX_RETAINED_SUPPRESSIONS",
    "NOTIFICATION_AUDIENCES",
    "NOTIFICATION_COOLDOWN_SECONDS",
    "NOTIFICATION_RATE_LIMIT_WINDOW_SECONDS",
    "NOTIFICATION_RECORD_DECISION",
    "NOTIFICATION_RECORD_REASON",
    "NOTIFICATION_RECORD_SEVERITY",
    "NOTIFICATION_RECORD_SINK",
    "NOTIFICATION_RECORD_SUBJECT",
    "NOTIFICATION_SEVERITIES",
    "NOTIFICATION_SINKS",
    "PAGING_SINKS",
    "PUSHOVER_MAX_MESSAGE_CHARS",
    "PUSHOVER_MAX_TITLE_CHARS",
    "PUSHOVER_MAX_URL_CHARS",
    "PUSHOVER_PRIORITY_EMERGENCY",
    "PUSHOVER_PRIORITY_HIGH",
    "PUSHOVER_PRIORITY_LOW",
    "PUSHOVER_PRIORITY_LOWEST",
    "PUSHOVER_PRIORITY_NORMAL",
    "PUSHOVER_SOUND_DEFAULT",
    "PUSHOVER_SOUND_PAGING",
    "QUIET_HOURS_END_HOUR",
    "QUIET_HOURS_START_HOUR",
    "REPORT_DELIVERY_BACKOFF_FACTOR",
    "REPORT_DELIVERY_BACKOFF_SECONDS",
    "REPORT_DELIVERY_MAX_BACKOFF_SECONDS",
    "REPORT_DESTINATIONS",
    "REPORT_MAX_DELIVERY_ATTEMPTS",
    "REPORT_SUMMARY_BUDGET_RATIO",
    "REPORT_SUMMARY_NOTICE",
    "SEVERITY_CRITICAL",
    "SEVERITY_HIGH",
    "SEVERITY_LOW",
    "SEVERITY_MEDIUM",
    "SEVERITY_NOISE",
    "SINK_CHAT",
    "SINK_EMAIL",
    "SINK_PAGERDUTY",
    "SINK_PUSHOVER",
    "SINK_WEBHOOK",
]
