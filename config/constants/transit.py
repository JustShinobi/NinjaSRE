"""What the deployment remembers about data in transit, and what it spends moving it.

Transit is the two seams where data crosses the deployment's boundary: a webhook
arriving, and a destination being told something. Both are bounded here rather
than at the seams themselves, because the two halves have to agree — a ledger
page the ingress screen can ask for and the outbound screen cannot would make
one column of the same screen behave differently from the other.

Three groups.

**How much transit is remembered.** One masked sample per source and a bounded
page of delivery rows. The sample is one because it answers "did the format
change", which is a question about the *last* payload; keeping ten would be
keeping nine payloads nobody asked about, and a payload is the most sensitive
thing this deployment ever holds.

**What the outbound half may spend.** A bounded number of attempts with a fixed
backoff schedule. Unbounded retry against a destination that is down is how a
notification system becomes the outage, and a schedule written here is one an
operator can read without reading the dispatcher.

**The vocabulary the rules and the destinations are written in.** Rule actions,
detail levels, and the closed set of events a destination may subscribe to.
These are strings in three places — the schema, the evaluator, and the console —
and a fourth spelling of one of them is a rule that silently never matches.
"""

from __future__ import annotations

from typing import Final

# --- The ledger -------------------------------------------------------------------

#: Delivery rows one ledger query may return. A screen's worth of transit, and
#: the same bound for both directions so the two columns page alike.
MAX_TRANSIT_PAGE_SIZE: Final[int] = 200

#: What a ledger query returns when the caller does not say. Enough to fill the
#: recent-rejections list without asking for the whole retained window.
DEFAULT_TRANSIT_PAGE_SIZE: Final[int] = 50

#: Masked payload samples kept per source. One, because the sample exists to
#: answer "did the format change" — a question about the last delivery. A second
#: one would be a stored payload nobody asked for, and a payload is the most
#: sensitive thing this deployment ever holds.
TRANSIT_SAMPLES_PER_SOURCE: Final[int] = 1

#: How much of a masked sample is kept. Alert payloads run to kilobytes and the
#: shape is visible in the first few; the cap is what stops one source's verbose
#: vendor from making the ledger the largest table in the deployment.
MAX_TRANSIT_SAMPLE_BYTES: Final[int] = 8_192

#: The marker appended to a sample that was cut at the cap, so a reader can tell
#: a truncated payload from a short one.
TRANSIT_SAMPLE_TRUNCATION_MARKER: Final = "…[truncated]"

#: How often a running storm refreshes its shed row, in sheds. A storm is one
#: fact rather than a thousand, so it gets one ledger row per shed window
#: carrying how many were dropped — and that row is rewritten every hundredth
#: shed rather than every shed, because a load shedder that spends a database
#: write per shed is doing the work it exists to refuse. The consequence is
#: stated rather than hidden: the count on the row can trail the storm by up to
#: this many deliveries while the storm is still running.
TRANSIT_SHED_LEDGER_INTERVAL: Final[int] = 100

#: How long delivery rows are kept. Long enough to answer "this stopped arriving
#: some time last month", short enough that a chatty source cannot grow the
#: table without bound.
RETENTION_DAYS_TRANSIT: Final[int] = 30

#: The window a source's per-source counts are reported over, and therefore what
#: "recently" means on the ingress column. A day, because that is the span an
#: operator asking "is this still arriving" has in mind.
TRANSIT_ACTIVITY_WINDOW_HOURS: Final[int] = 24

#: The window a source's own delivery *volume* is reported over on the intake
#: screen. A week, because "is this still arriving" (the day window above) and
#: "how much has been arriving" are different questions — a source that fires
#: twice a month reads as silent on the first and as exactly what it is on the
#: second.
TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS: Final[int] = 24 * 7

# --- Routing rules ----------------------------------------------------------------

#: Ordered rules one rule set may hold. Evaluation is a linear scan on the
#: ingress path, so the bound is what keeps a delivery's cost independent of how
#: many rules somebody accumulated.
MAX_ROUTING_RULES: Final[int] = 100

#: The identifier the catch-all rule carries when the default set is used. Named
#: so the ledger row, the simulation result and the screen agree on what caught
#: a delivery that matched nothing else.
DEFAULT_CATCH_ALL_RULE_ID: Final = "catch-all"

#: Open an investigation for this delivery — today's behaviour for every
#: verified delivery, and therefore the default catch-all action.
RULE_ACTION_INVESTIGATE: Final = "investigate"

#: Ledger the delivery and raise the incident, but start no run.
RULE_ACTION_RECORD_ONLY: Final = "record_only"

#: Ledger the delivery and do nothing else. Always with a reason: a silent
#: discard is how an alert disappears without anybody knowing it disappeared.
RULE_ACTION_DISCARD: Final = "discard"

#: Every action a rule may take. A rule naming anything else is refused at
#: validation rather than at the first delivery that matches it.
RULE_ACTIONS: Final[tuple[str, ...]] = (
    RULE_ACTION_INVESTIGATE,
    RULE_ACTION_RECORD_ONLY,
    RULE_ACTION_DISCARD,
)

# --- Outbound destinations --------------------------------------------------------

#: Destinations one deployment may declare. The dispatcher fans out to all of
#: them per event, so this is a bound on what one investigation concluding costs.
MAX_DESTINATIONS: Final[int] = 50

#: How many times one outbound delivery is attempted before it is left failed
#: for a person to re-send. Four: the first try plus the three backoff steps
#: below, which is a little over ten minutes of a destination being down.
MAX_OUTBOUND_ATTEMPTS: Final[int] = 4

#: How long the dispatcher waits before each retry, in order. Fixed rather than
#: computed, so "when will it try again" is answerable by reading one line.
OUTBOUND_RETRY_BACKOFF_SECONDS: Final[tuple[int, ...]] = (30, 120, 600)

#: An investigation reached a conclusion.
DELIVERY_EVENT_INVESTIGATION_CONCLUDED: Final = "investigation_concluded"

#: A remediation was proposed for a human to decide on.
DELIVERY_EVENT_REMEDIATION_PROPOSED: Final = "remediation_proposed"

#: Something is waiting for an approval. 061 supplies the proposal events that
#: join this one; the enum ships with it so a destination configured today keeps
#: meaning the same thing when they land.
DELIVERY_EVENT_APPROVAL_PENDING: Final = "approval_pending"

#: An ingress source stopped delivering, or started rejecting. The one event
#: that is about the platform rather than about an incident, and the reason a
#: never-delivering source can reach somebody who is not looking at the screen.
DELIVERY_EVENT_SOURCE_DEGRADED: Final = "source_degraded"

#: The closed set of events a destination may subscribe to. Closed on purpose:
#: an open one becomes a string somebody typed, and a destination subscribed to
#: a typo is a destination that is silently never notified.
DELIVERY_EVENTS: Final[tuple[str, ...]] = (
    DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
    DELIVERY_EVENT_REMEDIATION_PROPOSED,
    DELIVERY_EVENT_APPROVAL_PENDING,
    DELIVERY_EVENT_SOURCE_DEGRADED,
)

#: A short body plus a link back into the console, which the reader authenticates
#: against. The default, and the safe one: the detail stays behind the same
#: permission check the screen is behind.
DELIVERY_DETAIL_SUMMARY_WITH_LINK: Final = "summary_with_link"

#: The whole report in the message body. A deliberate choice for a channel the
#: operator has decided is as trusted as the console.
DELIVERY_DETAIL_FULL_REPORT: Final = "full_report"

#: Every detail level a destination may declare, safest first.
DELIVERY_DETAIL_LEVELS: Final[tuple[str, ...]] = (
    DELIVERY_DETAIL_SUMMARY_WITH_LINK,
    DELIVERY_DETAIL_FULL_REPORT,
)

#: How much of a report goes into a summary body. One screen of a chat client,
#: past which the link is what the reader uses anyway.
MAX_DELIVERY_SUMMARY_CHARS: Final[int] = 600

#: The reason a destination row carries when the catalogue holds no integration
#: that can deliver anything. Named so the screen, the route and the test say
#: the same sentence rather than three similar ones.
NO_DELIVERY_CHANNEL_REASON: Final = (
    "No configured integration can deliver a message. Connect a chat or "
    "notification integration in the catalogue, then declare a destination here."
)

# --- Configuration paths ----------------------------------------------------------

#: The configuration section transit lives in — the seventh, beside the six
#: 058 established. Named here so the schema, the editor and the screen agree.
CONFIG_SECTION_TRANSIT: Final = "transit"

#: Where the ordered rule set lives in the configuration tree.
CONFIG_PATH_ROUTING_RULES: Final = "transit.rules"

#: Where the declared destinations live in the configuration tree.
CONFIG_PATH_DESTINATIONS: Final = "transit.destinations"

# --- Audit ------------------------------------------------------------------------

#: The action recorded when a person re-sends a failed delivery by hand. A
#: re-send is a human act that puts a report in front of somebody, so it is
#: audited like every other one.
TRANSIT_AUDIT_ACTION_RESEND: Final = "delivery.resend"

#: What a re-send audit row names as the thing acted upon.
TRANSIT_AUDIT_RESOURCE_KIND: Final = "delivery"

__all__ = [
    "CONFIG_PATH_DESTINATIONS",
    "CONFIG_PATH_ROUTING_RULES",
    "CONFIG_SECTION_TRANSIT",
    "DEFAULT_CATCH_ALL_RULE_ID",
    "DEFAULT_TRANSIT_PAGE_SIZE",
    "DELIVERY_DETAIL_FULL_REPORT",
    "DELIVERY_DETAIL_LEVELS",
    "DELIVERY_DETAIL_SUMMARY_WITH_LINK",
    "DELIVERY_EVENTS",
    "DELIVERY_EVENT_APPROVAL_PENDING",
    "DELIVERY_EVENT_INVESTIGATION_CONCLUDED",
    "DELIVERY_EVENT_REMEDIATION_PROPOSED",
    "DELIVERY_EVENT_SOURCE_DEGRADED",
    "MAX_DELIVERY_SUMMARY_CHARS",
    "MAX_DESTINATIONS",
    "MAX_OUTBOUND_ATTEMPTS",
    "MAX_ROUTING_RULES",
    "MAX_TRANSIT_PAGE_SIZE",
    "MAX_TRANSIT_SAMPLE_BYTES",
    "NO_DELIVERY_CHANNEL_REASON",
    "OUTBOUND_RETRY_BACKOFF_SECONDS",
    "RETENTION_DAYS_TRANSIT",
    "RULE_ACTIONS",
    "RULE_ACTION_DISCARD",
    "RULE_ACTION_INVESTIGATE",
    "RULE_ACTION_RECORD_ONLY",
    "TRANSIT_ACTIVITY_WINDOW_HOURS",
    "TRANSIT_AUDIT_ACTION_RESEND",
    "TRANSIT_AUDIT_RESOURCE_KIND",
    "TRANSIT_SAMPLES_PER_SOURCE",
    "TRANSIT_SAMPLE_TRUNCATION_MARKER",
    "TRANSIT_SHED_LEDGER_INTERVAL",
    "TRANSIT_WEEKLY_VOLUME_WINDOW_HOURS",
]
