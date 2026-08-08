"""The set of things this deployment is responsible for, and how each is doing.

Nothing else in the platform holds this. There are integrations that can answer
questions about infrastructure, a knowledge graph that models service topology,
and runs that reference resources by string — what was missing is the noun in
between: a resource the system knows it is watching, with an identity that
survives a restart, a state that means something, and a history.

Four ideas hold the package together, and each of them is a decision that could
have gone the other way.

**Identity comes from the source, not the name.** ``identity`` derives a key
from the source integration and the provider's own identifier. A rename is an
update; a re-discovery finds the same row; two replicas deriving the key at the
same instant derive the same one.

**Absent is not unhealthy.** A resource that no longer exists has not failed,
and only a *successful* sweep may conclude it is gone. A failed sweep marks its
resources stale with the reason. That distinction is written into the storage
port's signatures rather than into the callers, because it is the single most
damaging thing this component could get wrong: an integration outage that
reported the whole estate as decommissioned would cascade into every detector
and every autonomy decision downstream.

**Health is derived and shows its work.** ``health`` maps provider statuses into
a closed set through declared mappings, keeps the raw value, records the signals
and the rule, and rolls a parent's state up from its children through a rule
that is visible on the parent. A status string copied into a column cannot be
compared across providers and cannot be explained.

**Relationships reuse the graph.** ``platform/knowledge``'s topology already
answers "what does this affect", and blast radius already traverses it. A second
graph would mean two answers to one question.

Storage is the estate repository port. Discovery is a protocol integrations
implement, invoked through the credential proxy like every other integration
call, and swept under the scheduler's existing lease-based claiming.
"""

from __future__ import annotations

__all__: list[str] = []
