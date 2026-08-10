"""What the platform asks a signal source, and what it will accept back.

A signal source is a system NinjaSRE *reads* during an investigation — a metric
store, a log store, a trace store, an alert router, a dashboard server. It is
not a system NinjaSRE runs, which is what separates this module from
``config.constants.observation`` (the deployment's own detection appetite) and
from ``config.constants.observability`` (the deployment's own logs).

Three groups.

**The six questions.** Every investigation of a resource asks some subset of
them, and each one has a right source and several wrong ones. Naming the set
here rather than in the code that derives it is what lets a question be added
without a second list somewhere disagreeing about how many there are.

**How a source is keyed.** The same resource is named differently by every
system that watches it: a hypervisor knows a guest by its numeric identifier, a
metric store by whatever label the exporter attached, a log store by a stream
label. A signal map entry carries which of these it is keyed by, because a query
built with the wrong key returns an empty result rather than an error.

**What verification demands.** A window long enough that a source with any
traffic at all has something in it, and short enough that stale data cannot
satisfy it; and how far a source's clock may be from the platform's before the
correlation it takes part in stops meaning anything.
"""

from __future__ import annotations

from typing import Final

# --- The six questions -------------------------------------------------------------

#: Is it running at all? Answered by whatever declares the resource's existence.
SIGNAL_QUESTION_UP: Final = "up"

#: Is it short of something? CPU, memory, disk, or the host underneath it.
SIGNAL_QUESTION_PRESSURE: Final = "pressure"

#: What did it write down?
SIGNAL_QUESTION_LOGS: Final = "logs"

#: What did it call, and how long did the call take?
SIGNAL_QUESTION_TRACES: Final = "traces"

#: What is complaining about it right now?
SIGNAL_QUESTION_FIRING: Final = "firing"

#: What would a person open to look at it?
SIGNAL_QUESTION_DASHBOARDS: Final = "dashboards"

#: The closed set, in the order a resource page reads them: what it is, how it
#: is doing, what it said, what it did, who is shouting, where to look.
SIGNAL_QUESTIONS: Final[tuple[str, ...]] = (
    SIGNAL_QUESTION_UP,
    SIGNAL_QUESTION_PRESSURE,
    SIGNAL_QUESTION_LOGS,
    SIGNAL_QUESTION_TRACES,
    SIGNAL_QUESTION_FIRING,
    SIGNAL_QUESTION_DASHBOARDS,
)

#: The two questions every resource must resolve or explain. A resource with no
#: answer to "is it up" is a row in an inventory rather than something the
#: deployment is responsible for, and one with no answer to "what did it write
#: down" cannot be investigated past its own status field.
SIGNAL_QUESTIONS_REQUIRED: Final[tuple[str, ...]] = (
    SIGNAL_QUESTION_UP,
    SIGNAL_QUESTION_LOGS,
)

# --- How a source is keyed ---------------------------------------------------------

#: The hypervisor's numeric identifier for a guest. The key host-side guest
#: series carry, and the only correct key for a container's resource usage.
SIGNAL_KEY_VMID: Final = "vmid"

#: The exporter's own idea of which machine it is scraping, usually host:port.
SIGNAL_KEY_INSTANCE: Final = "instance"

#: The resource's own name in the platform, for a source that indexes by name.
SIGNAL_KEY_NAME: Final = "name"

#: The resource's address on the network, for a source that indexes by host.
SIGNAL_KEY_ADDRESS: Final = "address"

SIGNAL_KEYS: Final[tuple[str, ...]] = (
    SIGNAL_KEY_VMID,
    SIGNAL_KEY_INSTANCE,
    SIGNAL_KEY_NAME,
    SIGNAL_KEY_ADDRESS,
)

# --- What verification demands -----------------------------------------------------

#: How far back a verification read looks. Fifteen minutes: longer than any
#: ordinary scrape or flush interval, so a working source cannot be empty across
#: it by timing alone, and short enough that a source which stopped collecting
#: an hour ago is not certified by its own history.
VERIFY_WINDOW_MINUTES: Final[int] = 15

#: How many records a verification read pulls before it stops counting. Small:
#: the only question is whether the answer was empty, and a setup screen that
#: dragged an incident's worth of log lines through the credential proxy to
#: establish that would be its own kind of failure.
VERIFY_WINDOW_SAMPLE_LIMIT: Final[int] = 5

#: How far a signal source's clock may be from the platform's before the
#: correlation it takes part in stops meaning anything. Thirty seconds, and the
#: number is about *correlation* rather than about protocol: the Proxmox
#: integration tolerates one second between cluster members because corosync's
#: token protocol does, whereas a metric store thirty seconds out still lines up
#: on the minute boundaries an investigation reasons in. Past this, "the alert
#: fired before the deploy" becomes a claim about two different clocks.
SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS: Final[float] = 30.0

__all__ = [
    "SIGNAL_KEYS",
    "SIGNAL_KEY_ADDRESS",
    "SIGNAL_KEY_INSTANCE",
    "SIGNAL_KEY_NAME",
    "SIGNAL_KEY_VMID",
    "SIGNAL_QUESTIONS",
    "SIGNAL_QUESTIONS_REQUIRED",
    "SIGNAL_QUESTION_DASHBOARDS",
    "SIGNAL_QUESTION_FIRING",
    "SIGNAL_QUESTION_LOGS",
    "SIGNAL_QUESTION_PRESSURE",
    "SIGNAL_QUESTION_TRACES",
    "SIGNAL_QUESTION_UP",
    "SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS",
    "VERIFY_WINDOW_MINUTES",
    "VERIFY_WINDOW_SAMPLE_LIMIT",
]
