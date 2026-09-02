"""What the estate is allowed to cost: sweep bounds, freshness, and page sizes.

Every number here is a ceiling on something a provider or an operator could
otherwise make unbounded. Discovery is the only part of the platform that walks
somebody else's inventory, so it is the only part where "one more page" is a
decision a remote system gets to make on our behalf — and the bounds below are
what takes that decision back.

The freshness intervals are the exception: they are not ceilings but *claims*.
Past its interval a resource's health is reported as stale rather than as what
it last was, so the interval is the deployment saying how long it is willing to
stand behind an observation. A hypervisor node polled every minute and a backup
job that runs nightly cannot share one number without one of them lying.
"""

from __future__ import annotations

from typing import Final

# --- The sweep ----------------------------------------------------------------

#: The job kind the scheduler stores for a discovery sweep. One string, so the
#: dispatcher, the executor, and the operator's job listing agree.
ESTATE_DISCOVERY_JOB_KIND: Final = "estate.discovery"

#: How often an integration is swept when it declares nothing. Fifteen minutes
#: is short enough that a guest created by hand appears while the operator is
#: still looking at the screen, and long enough that eighty integrations do not
#: become a poll every eleven seconds.
DEFAULT_DISCOVERY_INTERVAL_SECONDS: Final[int] = 900

#: The shortest interval an integration may declare. Below this a sweep is a
#: monitoring loop, and monitoring is feature-039 work with its own budget.
MIN_DISCOVERY_INTERVAL_SECONDS: Final[int] = 60

#: Wall-clock seconds one sweep may spend before it suspends and resumes at its
#: cursor. Suspension is the mitigation for ten thousand resources arriving at
#: once: the bound stays where it is and the work comes back.
MAX_SWEEP_SECONDS: Final[float] = 60.0

#: Provider calls one sweep may make. The second half of the same bound, because
#: a source that answers instantly can still be walked ten thousand times.
MAX_SWEEP_PROVIDER_CALLS: Final[int] = 200

#: Resources one sweep may ingest before suspending. A page bound rather than a
#: truncation: what is not ingested this time is ingested at the cursor next
#: time, and nothing is silently dropped.
MAX_SWEEP_RESOURCES: Final[int] = 5_000

#: How long a discovery lease is held before another replica may claim the
#: sweep. Longer than ``MAX_SWEEP_SECONDS`` so a sweep that runs to its own
#: bound is never reclaimed underneath itself.
DISCOVERY_LEASE_SECONDS: Final[float] = 120.0

# --- Freshness ----------------------------------------------------------------

#: How long a health observation stands when the kind declares nothing. Four
#: times the default sweep interval, so three consecutive failed sweeps are
#: needed before a resource reports stale — one missed poll is not evidence.
DEFAULT_FRESHNESS_SECONDS: Final[int] = 3_600

#: The shortest freshness interval a kind may declare. A kind whose observations
#: expire faster than the sweep that produces them would report stale forever.
MIN_FRESHNESS_SECONDS: Final[int] = 60

# --- Maintenance --------------------------------------------------------------

#: The longest maintenance window an operator may open in one go. Maintenance
#: suppresses a resource from the problem count, so an unbounded window is a
#: permanently hidden failure. Seven days is long enough for a hardware swap and
#: short enough that somebody has to renew it.
MAX_MAINTENANCE_SECONDS: Final[int] = 604_800

# --- Query --------------------------------------------------------------------

#: Resources one estate query may return. Separate from the shared page bound
#: because an estate listing is what a console table pages through, and it is
#: the one read whose natural size is "the whole estate".
MAX_ESTATE_PAGE_SIZE: Final[int] = 500

#: How many pages a whole-estate pass walks before it stops. The ceiling under
#: "page until the estate runs out": at the page bound above this is 25,000
#: resources, which is far past any deployment this platform is aimed at and
#: still a number rather than "until it ends". A pass with no ceiling is one
#: that turns an estate somebody grew into a request that never returns.
MAX_ESTATE_SWEEP_PAGES: Final[int] = 50

#: Seconds a summary over the whole estate may take. Declared here rather than
#: in the benchmark, so the budget and the assertion cannot drift apart.
ESTATE_SUMMARY_BUDGET_SECONDS: Final[float] = 1.0

#: The estate size the budgets are declared against. Ten thousand is the number
#: the specification names; a budget without the size it was measured at is not
#: a budget.
ESTATE_SUMMARY_BUDGET_RESOURCES: Final[int] = 10_000

#: Seconds the whole of a first connection may take — every suspended pass and
#: the one that completes — for an estate of ``ESTATE_SUMMARY_BUDGET_RESOURCES``.
#: Larger than the summary budget by two orders of magnitude on purpose:
#: discovery writes every row, derives every state, and does it more than once
#: because the sweep suspends. What it bounds is that a first connection
#: finishes at all, not that it is quick.
ESTATE_DISCOVERY_BUDGET_SECONDS: Final[float] = 120.0

#: Health transitions one resource's history returns by default.
DEFAULT_TRANSITION_HISTORY: Final[int] = 50

#: Signals one health derivation may carry. A derivation an operator cannot read
#: in one screen does not explain anything.
MAX_HEALTH_SIGNALS: Final[int] = 20

# --- Declared inventory, ingested for enrichment -------------------------------

#: Bytes one ingested inventory document may be. An operator points this at a
#: directory somebody else maintains, so the size of what arrives is not a
#: decision this deployment took — which is exactly the shape everything else in
#: this module bounds. A megabyte is two orders of magnitude above the reference
#: repository's largest file and small enough that a wrong path fails loudly
#: rather than filling memory.
MAX_ENRICHMENT_DOCUMENT_BYTES: Final[int] = 1_048_576

#: Entries one ingested document may declare. Separate from the byte bound
#: because a small file can still declare a hundred thousand hosts, and it is
#: the entry count that decides how much annotation work follows.
MAX_ENRICHMENT_ENTRIES: Final[int] = 5_000

# --- An alert's target, and the resource it is about ---------------------------

#: The labels that may name what an alert is about, in the order they are tried.
#:
#: Order is the whole of the rule. A host-side exporter labels a guest's series
#: with the *host's* address and the guest's number, so an alert about a
#: container carries both — and resolving the address first would produce an
#: investigation of the hypervisor about the container's memory. The numeric
#: identifier is the specific answer, so it is asked for first.
ALERT_TARGET_LABELS: Final[tuple[str, ...]] = ("vmid", "target", "instance", "host", "node")

#: The label whose value is a hypervisor guest's own number rather than an
#: address or a name. Named apart because it is the one that resolves by lookup
#: instead of by matching what the resource reports about itself.
ALERT_VMID_LABEL: Final = "vmid"

#: The prefix length an unmatched address is placed by when no zone map is
#: declared: the estate's own resources on the same network say which zone it
#: is. A /24 because that is how the reference estate is divided, and because a
#: wider inference would place an address in a zone by coincidence.
ALERT_ZONE_INFERENCE_PREFIX: Final[int] = 24

#: What the keys of an investigation's subject context are called.
#:
#: Written by the webhook router out of alert resolution, and read by capability
#: ranking and by the run itself. Constants rather than literals because the two
#: sides sit in different packages, and a key spelled one way in the writer and
#: another in the reader looks exactly like an alert that resolved to nothing.
SUBJECT_CONTEXT_RESOURCE_ID: Final = "resource_id"
SUBJECT_CONTEXT_RESOURCE_KIND: Final = "resource_kind"
SUBJECT_CONTEXT_RESOURCE_NAME: Final = "resource_name"
SUBJECT_CONTEXT_RESOURCE_SOURCE: Final = "resource_source"
#: What the vendor calls the subject, in the vendor's own vocabulary. The
#: identifier a vendor tool takes — as opposed to the resource id, which only
#: this deployment understands and which an agent handed nothing else will pass
#: to a vendor tool anyway, and be refused.
SUBJECT_CONTEXT_RESOURCE_NATIVE_ID: Final = "resource_native_id"
#: The resource the subject sits in, by name — the node a guest runs on. The
#: other half of what a per-guest vendor call needs.
SUBJECT_CONTEXT_RESOURCE_PARENT: Final = "resource_parent"
#: Where the subject answers. Usually what the alert matched on, and what ties
#: the subject back to the symptom that was reported.
SUBJECT_CONTEXT_RESOURCE_ADDRESS: Final = "resource_address"
SUBJECT_CONTEXT_RESOURCE_ZONE: Final = "resource_zone"
SUBJECT_CONTEXT_RESOLVED_FROM: Final = "resolved_from"

#: Alert labels that carry something ranking can match a declaration against.
#:
#: ``service`` and ``job`` name what the alert is about in the sender's own
#: vocabulary, and a capability's tags are written in the same one. ``severity``
#: is excluded deliberately: every capability that mentions "critical" would
#: match every critical alert, which is noise wearing a signal's clothes.
ALERT_RANKING_TAG_LABELS: Final[tuple[str, ...]] = ("service", "job", "alertname")

#: The label a sender uses to say which domain an alert belongs to, when it
#: says so at all. Matched against a capability's declared domain.
ALERT_DOMAIN_LABEL: Final = "domain"

#: Unresolved alert targets one listing returns. A finding per alert that
#: named something unknown, and a deployment pointed at the wrong receiver can
#: produce them faster than anybody reads them.
MAX_UNRESOLVED_ALERT_TARGETS: Final[int] = 50

# --- Retention ----------------------------------------------------------------

#: How long estate history is kept when the operator configures nothing. Longer
#: than a run trace, because "when did this node start flapping" is a question
#: asked months later, and shorter than an episode, because the transitions are
#: not what learning is measured against.
RETENTION_DAYS_ESTATE_HISTORY: Final[int] = 180

# --- The overview's daily sparkline --------------------------------------------

#: Days of daily estate snapshots `GET /v1/overview` draws a sparkline point
#: from, and the bound `EstateSnapshotStore.list_daily` refuses to page past.
#: Fourteen, because the overview's own KPI tiles are a two-week trend rather
#: than a full history — the same window the reference dashboard draws.
MAX_OVERVIEW_DAILY_BUCKETS: Final[int] = 14

#: How long one organisation's overview is served as computed before it is
#: computed again. The five tiles are figures over a fourteen-day window —
#: draining every incident and every run in it, the estate's summary and the
#: daily snapshots — and the dashboard is the first screen every session
#: opens. The view carries ``captured_at``, so a reader is told which instant
#: the figures describe; fifteen seconds is well inside how often the window
#: itself changes shape.
OVERVIEW_CACHE_TTL_SECONDS: Final[float] = 15.0

__all__ = [
    "ALERT_DOMAIN_LABEL",
    "ALERT_RANKING_TAG_LABELS",
    "ALERT_TARGET_LABELS",
    "ALERT_VMID_LABEL",
    "ALERT_ZONE_INFERENCE_PREFIX",
    "DEFAULT_DISCOVERY_INTERVAL_SECONDS",
    "DEFAULT_FRESHNESS_SECONDS",
    "DEFAULT_TRANSITION_HISTORY",
    "DISCOVERY_LEASE_SECONDS",
    "ESTATE_DISCOVERY_BUDGET_SECONDS",
    "ESTATE_DISCOVERY_JOB_KIND",
    "ESTATE_SUMMARY_BUDGET_RESOURCES",
    "ESTATE_SUMMARY_BUDGET_SECONDS",
    "MAX_ENRICHMENT_DOCUMENT_BYTES",
    "MAX_ENRICHMENT_ENTRIES",
    "MAX_ESTATE_PAGE_SIZE",
    "MAX_ESTATE_SWEEP_PAGES",
    "MAX_HEALTH_SIGNALS",
    "MAX_MAINTENANCE_SECONDS",
    "MAX_OVERVIEW_DAILY_BUCKETS",
    "OVERVIEW_CACHE_TTL_SECONDS",
    "MAX_SWEEP_PROVIDER_CALLS",
    "MAX_SWEEP_RESOURCES",
    "MAX_SWEEP_SECONDS",
    "MAX_UNRESOLVED_ALERT_TARGETS",
    "MIN_DISCOVERY_INTERVAL_SECONDS",
    "MIN_FRESHNESS_SECONDS",
    "RETENTION_DAYS_ESTATE_HISTORY",
    "SUBJECT_CONTEXT_RESOLVED_FROM",
    "SUBJECT_CONTEXT_RESOURCE_ADDRESS",
    "SUBJECT_CONTEXT_RESOURCE_ID",
    "SUBJECT_CONTEXT_RESOURCE_KIND",
    "SUBJECT_CONTEXT_RESOURCE_NAME",
    "SUBJECT_CONTEXT_RESOURCE_NATIVE_ID",
    "SUBJECT_CONTEXT_RESOURCE_PARENT",
    "SUBJECT_CONTEXT_RESOURCE_SOURCE",
    "SUBJECT_CONTEXT_RESOURCE_ZONE",
]
