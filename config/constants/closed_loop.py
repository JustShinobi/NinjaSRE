"""Bounds for the half of remediation that happens after the change.

Acting is feature 017's; finding out whether it worked is this one's, and the
numbers below are what "finding out" costs. Four groups, and three of them
encode a judgement worth stating rather than a limit somebody picked.

**Settle periods.** A signal read immediately after a change reports the state
the change was made to fix, so every verification waits. The floor is not a
performance bound — it is the shortest interval over which any of the
deployment's sources produce a second sample, and a settle period below it would
verify against the reading that was already there.

**The noise floor.** A signal that moved by less than
``VERIFICATION_MINIMUM_CHANGE`` did not move enough to conclude anything from,
and the outcome is ``inconclusive``. Reporting such a move as success is the
single most damaging thing this feature could do, because it produces a high
reported success rate and an operator who stops believing it.

**Recurrence.** Four occurrences in thirty days is the point at which the
deployment stops treating something as an incident to fix and raises it as a
problem that needs a change. Both numbers are overridable per capability through
the config service, because a window that is wrong is visible only in use.
"""

from __future__ import annotations

from typing import Final

# --- Settle periods and verification timing ----------------------------------

#: How long a capability waits, by default, before its declared signals are
#: worth reading. Five minutes: long enough for a metrics pipeline to produce a
#: second sample of anything, short enough that an operator watching an incident
#: does not conclude nothing is happening.
DEFAULT_SETTLE_SECONDS: Final[int] = 300

#: The shortest settle period a capability may declare. Below this the
#: verification reads the same sample the detector fired on, which is a
#: measurement of nothing dressed up as a verdict.
MIN_SETTLE_SECONDS: Final[int] = 30

#: The longest. A verification that has not concluded within four hours is not
#: going to, and an obligation with a longer horizon is one nobody will connect
#: to the action that created it.
MAX_SETTLE_SECONDS: Final[int] = 4 * 60 * 60

#: How long a worker's lease on one verification obligation lasts. Longer than
#: any single verification takes and far shorter than a settle period, so a
#: worker that died leaves its obligation to the next one within a minute.
VERIFICATION_LEASE_SECONDS: Final[float] = 60.0

#: How many due obligations one worker claims at a time. A worker that claimed
#: the whole backlog would leave every other replica idle and then drop the lot
#: when it restarted — the reason ``MAX_JOB_CLAIM_BATCH`` exists, for the same
#: mechanism.
MAX_VERIFICATION_CLAIM_BATCH: Final[int] = 25

#: How many times a verification may be re-attempted before it is recorded as
#: inconclusive and left alone. Attempts happen when the lease expired under a
#: worker rather than when the signals were unhelpful, so this is a bound on
#: crashing, not on waiting.
MAX_VERIFICATION_ATTEMPTS: Final[int] = 3

# --- What counts as an effect ------------------------------------------------

#: The smallest relative move that is evidence of anything, as a fraction of the
#: value before the action. Ten per cent: below that, a signal on a live system
#: is indistinguishable from an unrelated fluctuation, and the honest verdict is
#: ``inconclusive`` rather than either success or failure.
VERIFICATION_MINIMUM_CHANGE: Final[float] = 0.10

#: The five outcomes a verification may reach. A closed set, exported so the
#: policy schema, the API response and the console all validate against one
#: list — a sixth spelling appearing in any of them is a verdict nothing else
#: can read.
VERIFICATION_EFFECTIVE: Final = "effective"
VERIFICATION_INEFFECTIVE: Final = "ineffective"
VERIFICATION_WORSENED: Final = "worsened"
VERIFICATION_INCONCLUSIVE: Final = "inconclusive"
VERIFICATION_UNVERIFIABLE: Final = "unverifiable"

VERIFICATION_VERDICTS: Final[tuple[str, ...]] = (
    VERIFICATION_EFFECTIVE,
    VERIFICATION_INEFFECTIVE,
    VERIFICATION_WORSENED,
    VERIFICATION_INCONCLUSIVE,
    VERIFICATION_UNVERIFIABLE,
)

# --- Recurrence --------------------------------------------------------------

#: How many identical remediations inside the window raise a recurring problem.
#: Four, because three is the count at which a human still reasonably believes
#: in coincidence and five is the count at which they have stopped reading the
#: incidents.
DEFAULT_RECURRENCE_THRESHOLD: Final[int] = 4

#: The window the count is taken over. Thirty days: a monthly cycle is the
#: shortest period over which "this keeps happening" is a claim about the system
#: rather than about one bad night.
DEFAULT_RECURRENCE_WINDOW_SECONDS: Final[int] = 30 * 24 * 60 * 60

#: The largest window a deployment may declare. Beyond a year the count stops
#: describing the system that exists now.
MAX_RECURRENCE_WINDOW_SECONDS: Final[int] = 365 * 24 * 60 * 60

# --- Query bounds ------------------------------------------------------------

#: The page bound on an effectiveness listing. Its own bound rather than the
#: shared query one, and smaller: this is read to answer "has this worked here
#: before", which is a question about the recent past, and a caller wanting the
#: whole corpus wants the aggregate instead.
MAX_EFFECTIVENESS_PAGE_SIZE: Final[int] = 100

#: How long an effectiveness question may take over a year of history, in
#: seconds. Declared rather than hoped for: the query is on the path of every
#: proposal, and a proposal that waits on it is an investigation that stalls.
#: ``tests/benchmarks`` asserts it against a year of records.
EFFECTIVENESS_QUERY_BUDGET_SECONDS: Final[float] = 0.5

#: The page bound on a recurring-problem listing.
MAX_RECURRING_PROBLEM_PAGE_SIZE: Final[int] = 100

# --- The audit trail ---------------------------------------------------------

#: One verification reached a verdict.
CLOSED_LOOP_AUDIT_ACTION_VERIFIED: Final = "remediation.verified"

#: A rollback was triggered by a verification rather than by a person.
CLOSED_LOOP_AUDIT_ACTION_ROLLED_BACK: Final = "remediation.auto_rollback"

#: Autonomy on one resource was suspended, and by what.
CLOSED_LOOP_AUDIT_ACTION_SUSPENDED: Final = "remediation.autonomy_suspended"

#: A human cleared that suspension. The pair is the whole record of the
#: suspension: the state is the later of the two, which is why they are two
#: append-only rows rather than one mutable flag.
CLOSED_LOOP_AUDIT_ACTION_CLEARED: Final = "remediation.autonomy_cleared"

#: A recurring problem was raised from the count.
CLOSED_LOOP_AUDIT_ACTION_RECURRENCE: Final = "remediation.recurrence_raised"

#: What the suspension rows are keyed by. The resource, because a suspension is
#: about the thing whose state nobody is sure of.
CLOSED_LOOP_AUDIT_RESOURCE_KIND: Final = "remediation_resource"

#: How many suspension rows one resource's state is read from. A suspension is
#: raised and cleared a handful of times in the life of a resource; the bound
#: only ever caps what asking costs.
MAX_SUSPENSION_ROWS: Final[int] = 50

#: Where the reason lives inside a suspension row's detail.
SUSPENSION_DETAIL_REASON: Final = "reason"

#: Where the action that caused the suspension lives.
SUSPENSION_DETAIL_ACTION: Final = "action_id"

# --- Scheduling --------------------------------------------------------------

#: The kind of the recurring job that sweeps due verification obligations. One
#: per deployment, claimed through the scheduler exactly as the observation tick
#: is, which is what hands the sweep across the tenant boundary without this
#: package inventing a second way to do it.
VERIFICATION_SWEEP_JOB_KIND: Final = "remediation.verification_sweep"

#: How often that job runs. Shorter than the shortest settle period, so an
#: obligation is never more than one sweep late.
VERIFICATION_SWEEP_INTERVAL_SECONDS: Final[int] = 30

#: How long a worker's lease on the sweep job lasts. Longer than the sweep's own
#: budget, so a sweep that ran to its ceiling is never reclaimed underneath
#: itself.
VERIFICATION_SWEEP_LEASE_SECONDS: Final[float] = 120.0

# --- Serialising two remediations against one resource -----------------------

#: How long a durable hold on one resource lasts before another replica may take
#: it. A lease rather than a lock, for the reason the scheduler's claims are: a
#: lock that outlives the process holding it needs a human to clear it, and it
#: will be a human who is already busy.
RESOURCE_HOLD_LEASE_SECONDS: Final[float] = 300.0

#: What the second arrival does when a resource is already held. Declared, per
#: FR-021, rather than left to whichever branch runs first.
SECOND_ARRIVAL_WAIT: Final = "wait"
SECOND_ARRIVAL_REFUSE: Final = "refuse"
SECOND_ARRIVALS: Final[tuple[str, ...]] = (SECOND_ARRIVAL_WAIT, SECOND_ARRIVAL_REFUSE)


__all__ = [
    "CLOSED_LOOP_AUDIT_ACTION_CLEARED",
    "CLOSED_LOOP_AUDIT_ACTION_RECURRENCE",
    "CLOSED_LOOP_AUDIT_ACTION_ROLLED_BACK",
    "CLOSED_LOOP_AUDIT_ACTION_SUSPENDED",
    "CLOSED_LOOP_AUDIT_ACTION_VERIFIED",
    "CLOSED_LOOP_AUDIT_RESOURCE_KIND",
    "DEFAULT_RECURRENCE_THRESHOLD",
    "DEFAULT_RECURRENCE_WINDOW_SECONDS",
    "DEFAULT_SETTLE_SECONDS",
    "EFFECTIVENESS_QUERY_BUDGET_SECONDS",
    "MAX_EFFECTIVENESS_PAGE_SIZE",
    "MAX_RECURRENCE_WINDOW_SECONDS",
    "MAX_RECURRING_PROBLEM_PAGE_SIZE",
    "MAX_SETTLE_SECONDS",
    "MAX_SUSPENSION_ROWS",
    "MAX_VERIFICATION_ATTEMPTS",
    "MAX_VERIFICATION_CLAIM_BATCH",
    "MIN_SETTLE_SECONDS",
    "RESOURCE_HOLD_LEASE_SECONDS",
    "SECOND_ARRIVAL_REFUSE",
    "SECOND_ARRIVAL_WAIT",
    "SECOND_ARRIVALS",
    "SUSPENSION_DETAIL_ACTION",
    "SUSPENSION_DETAIL_REASON",
    "VERIFICATION_EFFECTIVE",
    "VERIFICATION_INCONCLUSIVE",
    "VERIFICATION_INEFFECTIVE",
    "VERIFICATION_LEASE_SECONDS",
    "VERIFICATION_MINIMUM_CHANGE",
    "VERIFICATION_SWEEP_INTERVAL_SECONDS",
    "VERIFICATION_SWEEP_JOB_KIND",
    "VERIFICATION_SWEEP_LEASE_SECONDS",
    "VERIFICATION_UNVERIFIABLE",
    "VERIFICATION_VERDICTS",
    "VERIFICATION_WORSENED",
]
