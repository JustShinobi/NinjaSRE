"""What watching costs: signal retention, detector bounds, and dispatch ceilings.

Detection is the first part of the platform that starts work nobody asked for.
That makes every number here a bound on the deployment's own appetite rather
than on a remote system's — which is the opposite of ``config.constants.estate``
and is why the two do not share a module.

Three groups, and they answer three different questions.

**How much history is kept.** A detector reads a window, so signals must survive
at least the longest window any detector declares and no longer. Retention is
therefore derived from the declarations rather than configured beside them: an
operator who lengthens a window and forgets to lengthen retention would get a
detector that can never fire.

**How hard a detector may be pushed.** A duration floor, a flap window, and a
crossing count. Without the floor a detector with a zero-second duration fires
on one sample, which is the definition of a false alarm; without the flap
bounds, a signal oscillating across its threshold produces one incident per
crossing and the operator stops reading them.

**How much work a firing may start.** Rate limits per team and globally, applied
before the first storm rather than after it. A node going down takes its guests
with it, and correlation handles most of that — the limit is what handles a
cause correlation cannot see.
"""

from __future__ import annotations

from typing import Final

# --- The tick -------------------------------------------------------------------

#: The job kind the scheduler stores for one evaluation tick. One string, so the
#: dispatcher, the worker, and an operator's job listing agree.
OBSERVATION_TICK_JOB_KIND: Final = "observation.tick"

#: How often the estate is evaluated when nothing says otherwise. A minute is
#: short enough that a datastore filling is caught while it is still filling,
#: and long enough that the tick is not the deployment's dominant cost.
DEFAULT_TICK_INTERVAL_SECONDS: Final[int] = 60

#: The shortest tick an operator may configure. Below this the tick overlaps
#: itself at estate scale, and an evaluation that starts before the last one
#: finished is two replicas of the same worker with none of the coordination.
MIN_TICK_INTERVAL_SECONDS: Final[int] = 15

#: How long an evaluation lease is held before another replica may claim the
#: tick. Longer than ``OBSERVATION_TICK_BUDGET_SECONDS`` so a tick that runs to
#: its own budget is never reclaimed underneath itself.
OBSERVATION_LEASE_SECONDS: Final[float] = 120.0

# --- Signals ----------------------------------------------------------------------

#: How often a poller calls its integration when the declaration says nothing.
DEFAULT_POLL_INTERVAL_SECONDS: Final[int] = 60

#: The shortest poll an integration may declare. Detection must add no provider
#: calls beyond what its pollers make, so this is the floor under that promise.
MIN_POLL_INTERVAL_SECONDS: Final[int] = 15

#: Signals one query may return. A detector reads a window, and a window that
#: does not fit in one page is a window whose verdict depends on paging.
MAX_SIGNAL_PAGE_SIZE: Final[int] = 2_000

#: The longest window a detector may declare, and therefore the retention floor.
#: Twenty-four hours: long enough for "this has been climbing all day", short
#: enough that one signal per resource per minute stays a bounded table.
MAX_DETECTOR_WINDOW_SECONDS: Final[int] = 86_400

#: How long a signal is kept when no detector declares a longer window. The
#: retention sweep uses the longest declared window when it is larger, and this
#: when it is not — so a deployment with no detectors still bounds its table.
DEFAULT_SIGNAL_RETENTION_SECONDS: Final[int] = 7_200

#: How much later than its interval a signal may arrive before the source counts
#: as silent. One missed poll is a network hiccup; three is a source that
#: stopped, and an absence detector that fired on the first would fire daily.
SIGNAL_SILENCE_TOLERANCE_INTERVALS: Final[int] = 3

# --- Detectors --------------------------------------------------------------------

#: The four condition kinds, as configuration spells them. Repeated here rather
#: than imported from the enum because ``config/`` imports nothing first-party —
#: which is the tier rule, and also what lets the schema validate a document
#: without loading the evaluator.
DETECTOR_KIND_THRESHOLD: Final = "threshold"
DETECTOR_KIND_ABSENCE: Final = "absence"
DETECTOR_KIND_RATE_OF_CHANGE: Final = "rate_of_change"
DETECTOR_KIND_STATE_TRANSITION: Final = "state_transition"
DETECTOR_CONDITION_KINDS: Final[tuple[str, ...]] = (
    DETECTOR_KIND_THRESHOLD,
    DETECTOR_KIND_ABSENCE,
    DETECTOR_KIND_RATE_OF_CHANGE,
    DETECTOR_KIND_STATE_TRANSITION,
)

#: Which side of a threshold fires.
DETECTOR_COMPARISON_ABOVE: Final = "above"
DETECTOR_COMPARISON_BELOW: Final = "below"
DETECTOR_COMPARISONS: Final[tuple[str, ...]] = (
    DETECTOR_COMPARISON_ABOVE,
    DETECTOR_COMPARISON_BELOW,
)

#: How many incidents one firing across many resources becomes.
DETECTOR_GROUPING_DETECTOR: Final = "detector"
DETECTOR_GROUPING_PARENT: Final = "parent"
DETECTOR_GROUPING_RESOURCE: Final = "resource"
DETECTOR_GROUPINGS: Final[tuple[str, ...]] = (
    DETECTOR_GROUPING_DETECTOR,
    DETECTOR_GROUPING_PARENT,
    DETECTOR_GROUPING_RESOURCE,
)

#: How long a condition holds before it fires, when a detector declares nothing.
#: Five minutes: long enough that a scrape blip does not open an incident, short
#: enough that a datastore filling is caught while it is still filling.
DEFAULT_DETECTOR_DURATION_SECONDS: Final[int] = 300

#: The shortest duration a condition may be required to hold. A detector with no
#: duration fires on one sample, which is a threshold crossing rather than a
#: problem.
MIN_DETECTOR_DURATION_SECONDS: Final[int] = 30

#: How far back flapping is counted. Two crossings an hour apart are two events;
#: two crossings a minute apart are one unstable signal.
FLAP_WINDOW_SECONDS: Final[int] = 900

#: Crossings inside ``FLAP_WINDOW_SECONDS`` that make a signal flapping rather
#: than firing. Three, because two is an ordinary recovery followed by an
#: ordinary relapse.
FLAP_CROSSING_THRESHOLD: Final[int] = 3

#: Detectors one deployment may declare. A bound rather than a guess: a hundred
#: is what the evaluation budget is measured against, and a deployment past it
#: has built a rules engine.
MAX_DETECTORS: Final[int] = 100

#: Characters a detector identifier may run to. It appears in a correlation key,
#: a job payload, and an operator's console, and all three read better short.
MAX_DETECTOR_ID_CHARS: Final[int] = 64

# --- Incidents ----------------------------------------------------------------------

#: Subjects one incident may carry. One cause across an estate is one incident
#: with many subjects, and this is the point past which the estate itself is the
#: subject and naming every member says nothing.
MAX_INCIDENT_SUBJECTS: Final[int] = 500

#: Timeline entries one incident may carry. Every state change is recorded, and
#: an incident that has changed state a thousand times is a loop, not a history.
MAX_INCIDENT_TIMELINE: Final[int] = 500

#: Incidents one listing may return.
MAX_INCIDENT_PAGE_SIZE: Final[int] = 200

#: How many pages a whole-window incident pass walks before it stops. The
#: ceiling under "page until the window runs out": at the page bound above this
#: is 5,000 incidents in one window, far past any fortnight a deployment this
#: platform is aimed at survives, and still a number rather than "until it
#: ends". A pass with no ceiling turns a noisy fortnight into a request that
#: never returns.
MAX_INCIDENT_SWEEP_PAGES: Final[int] = 25

#: How long a closed incident is kept. Longer than a run trace, because "has
#: this happened before" is asked months later.
RETENTION_DAYS_INCIDENTS: Final[int] = 180

# --- Dispatch -----------------------------------------------------------------------

#: Investigations one team's incidents may start in an hour. A hundred
#: simultaneous incidents must not become a hundred simultaneous runs, and a
#: team is the unit an operator budgets in.
MAX_DISPATCHES_PER_TEAM_PER_HOUR: Final[int] = 20

#: Investigations the whole deployment may start from incidents in an hour. The
#: second half of the same bound: fifty teams under their own limits are still
#: an unbounded deployment.
MAX_DISPATCHES_PER_HOUR: Final[int] = 60

# --- The budget ------------------------------------------------------------------

#: Seconds one evaluation tick may take at the declared size below. Declared
#: here rather than in the benchmark, so the budget and the assertion cannot
#: drift apart.
OBSERVATION_TICK_BUDGET_SECONDS: Final[float] = 10.0

#: The estate size the tick budget is declared against.
OBSERVATION_TICK_BUDGET_RESOURCES: Final[int] = 10_000

#: The detector count the tick budget is declared against.
OBSERVATION_TICK_BUDGET_DETECTORS: Final[int] = 100

__all__ = [
    "DEFAULT_DETECTOR_DURATION_SECONDS",
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_SIGNAL_RETENTION_SECONDS",
    "DEFAULT_TICK_INTERVAL_SECONDS",
    "DETECTOR_COMPARISONS",
    "DETECTOR_COMPARISON_ABOVE",
    "DETECTOR_COMPARISON_BELOW",
    "DETECTOR_CONDITION_KINDS",
    "DETECTOR_GROUPINGS",
    "DETECTOR_GROUPING_DETECTOR",
    "DETECTOR_GROUPING_PARENT",
    "DETECTOR_GROUPING_RESOURCE",
    "DETECTOR_KIND_ABSENCE",
    "DETECTOR_KIND_RATE_OF_CHANGE",
    "DETECTOR_KIND_STATE_TRANSITION",
    "DETECTOR_KIND_THRESHOLD",
    "FLAP_CROSSING_THRESHOLD",
    "FLAP_WINDOW_SECONDS",
    "MAX_DETECTORS",
    "MAX_DETECTOR_ID_CHARS",
    "MAX_DETECTOR_WINDOW_SECONDS",
    "MAX_DISPATCHES_PER_HOUR",
    "MAX_DISPATCHES_PER_TEAM_PER_HOUR",
    "MAX_INCIDENT_PAGE_SIZE",
    "MAX_INCIDENT_SUBJECTS",
    "MAX_INCIDENT_SWEEP_PAGES",
    "MAX_INCIDENT_TIMELINE",
    "MAX_SIGNAL_PAGE_SIZE",
    "MIN_DETECTOR_DURATION_SECONDS",
    "MIN_POLL_INTERVAL_SECONDS",
    "MIN_TICK_INTERVAL_SECONDS",
    "OBSERVATION_LEASE_SECONDS",
    "OBSERVATION_TICK_BUDGET_DETECTORS",
    "OBSERVATION_TICK_BUDGET_RESOURCES",
    "OBSERVATION_TICK_BUDGET_SECONDS",
    "OBSERVATION_TICK_JOB_KIND",
    "RETENTION_DAYS_INCIDENTS",
    "SIGNAL_SILENCE_TOLERANCE_INTERVALS",
]
