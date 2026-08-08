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

# --- Retention ----------------------------------------------------------------

#: How long estate history is kept when the operator configures nothing. Longer
#: than a run trace, because "when did this node start flapping" is a question
#: asked months later, and shorter than an episode, because the transitions are
#: not what learning is measured against.
RETENTION_DAYS_ESTATE_HISTORY: Final[int] = 180

__all__ = [
    "DEFAULT_DISCOVERY_INTERVAL_SECONDS",
    "DEFAULT_FRESHNESS_SECONDS",
    "DEFAULT_TRANSITION_HISTORY",
    "DISCOVERY_LEASE_SECONDS",
    "ESTATE_DISCOVERY_BUDGET_SECONDS",
    "ESTATE_DISCOVERY_JOB_KIND",
    "ESTATE_SUMMARY_BUDGET_RESOURCES",
    "ESTATE_SUMMARY_BUDGET_SECONDS",
    "MAX_ESTATE_PAGE_SIZE",
    "MAX_HEALTH_SIGNALS",
    "MAX_MAINTENANCE_SECONDS",
    "MAX_SWEEP_PROVIDER_CALLS",
    "MAX_SWEEP_RESOURCES",
    "MAX_SWEEP_SECONDS",
    "MIN_DISCOVERY_INTERVAL_SECONDS",
    "MIN_FRESHNESS_SECONDS",
    "RETENTION_DAYS_ESTATE_HISTORY",
]
