"""The assembly: what a homelab deployment watches, how much it may do, and who it tells.

Everything below this package is general machinery — a detector engine, an
autonomy gate, a notification policy, an incident lifecycle. None of it decides
anything. This package is where the decisions are made for the deployment an
individual actually runs: which detectors are on, at what thresholds, how
autonomous it is on the day it is installed, and what happens when it needs to
reach somebody who is not on a rota.

Six properties hold across the whole package.

**Propose-only is the default.** An autonomous system that acts on somebody's
home infrastructure on the day it is installed will eventually do something they
did not expect, and they will turn it off. The recommended posture is one named
preset away, and applying it shows what it would have done to the last week
first.

**Every shipped threshold states its reasoning.** A number with no reason beside
it is one an operator will either ignore or obey without understanding, and both
are worse than not shipping it. A detector missing its rationale fails a test
rather than a review.

**Two-node behaviour is detected, never presumed.** The cluster this was built
for has two nodes. A three-node cluster given two-node warnings learns to ignore
warnings, and a single-node installation given cluster detectors gets an
incident about quorum it has none of.

**Notification is for a person, not a rota.** Escalation is bounded and ends,
storms become one digest, and a resolution is sent even when the original was
never acknowledged — because the operator was at work.

**The heartbeat is not optional.** A guardian that has stopped looks exactly like
a cluster with no problems. An outbound push on an interval is what makes silence
detectable by the operator's own phone rather than by the system that is not
running.

**Where the operator has a declarative control plane, this reads it and never
writes to it.** A second writer over the same infrastructure is how drift becomes
an outage, so a remediation whose correct form is a change to that repository is
proposed as such.
"""

from __future__ import annotations

__all__: list[str] = []
