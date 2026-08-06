"""The two switches that make "topology helps" and "runbooks help" separate claims.

Article VII forbids claiming a mechanism that has not been measured, and this
feature ships two mechanisms that happen to live in one package. Folding them
into one switch would make the only available baseline "neither", and the two
questions an operator actually has — is it worth populating the graph, is it
worth writing the runbooks — would both come back as one number that answers
neither.

So the switches are independent, and the interesting runs are the two middles: a
graph the agent may not consult, and a corpus of runbooks it may not search. Each
isolates one store's contribution while the other stays exactly as it was.

"Off" means the guidance is not appended and the retrieval path is not reachable
— the same code path a deployment that never configured the store takes. A switch
that left a hook installed and returned early would still dispatch, still appear
in the trace, and still perturb the ordering a trajectory comparison reads.

Per-team resolution is a static default until the hierarchical configuration
service exists. ``for_team`` is the seam it will fill.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from config.constants.knowledge import NINJASRE_KNOWLEDGE_ENV, NINJASRE_TOPOLOGY_ENV

#: The names the evaluation harness enumerates as ablation axes. Strings rather
#: than an enum, because an axis is identified in a results table and a report
#: and both of those are text.
TOPOLOGY_SWITCH = "topology"
KNOWLEDGE_SWITCH = "knowledge_base"

KNOWLEDGE_SWITCHES: tuple[str, ...] = (TOPOLOGY_SWITCH, KNOWLEDGE_SWITCH)

#: Values that read as "off" in an environment variable. Anything else is on,
#: including a typo — a mis-spelled value must not silently disable a store and
#: leave an ablation table reporting a result it never measured.
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class KnowledgePolicy:
    """One team's topology and knowledge-base switches.

    Frozen. ``without`` returns a new policy rather than mutating this one, so an
    ablation run cannot leave a switch flipped for the run after it — which is
    exactly the bug that would make the table quietly wrong.
    """

    topology_enabled: bool = True
    knowledge_enabled: bool = True

    @property
    def enabled(self) -> bool:
        """Return whether either store does anything under this policy."""
        return self.topology_enabled or self.knowledge_enabled

    @classmethod
    def for_team(
        cls,
        *,
        topology_enabled: bool = True,
        knowledge_enabled: bool = True,
    ) -> KnowledgePolicy:
        """Return the policy for one team.

        The seam the configuration service fills. Until it exists every team
        resolves to what the caller states, which is the honest version of
        "per-team" before there is anywhere to store a per-team value.
        """
        return cls(topology_enabled=topology_enabled, knowledge_enabled=knowledge_enabled)

    @classmethod
    def from_environment(cls) -> KnowledgePolicy:
        """Return the policy an operator configured through the environment."""
        return cls(
            topology_enabled=_switch(os.environ.get(NINJASRE_TOPOLOGY_ENV)),
            knowledge_enabled=_switch(os.environ.get(NINJASRE_KNOWLEDGE_ENV)),
        )

    @classmethod
    def disabled(cls) -> KnowledgePolicy:
        """Return the policy the baseline with neither store runs under."""
        return cls(topology_enabled=False, knowledge_enabled=False)

    def without(self, *switches: str) -> KnowledgePolicy:
        """Return this policy with ``switches`` turned off.

        Raises on a switch nobody defined. An ablation that silently ignored an
        unknown axis would publish a table saying it measured something it never
        varied, which is worse than not measuring it at all.
        """
        unknown = set(switches) - set(KNOWLEDGE_SWITCHES)
        if unknown:
            raise ValueError(
                f"unknown knowledge switch(es) {', '.join(sorted(unknown))}; "
                f"expected one of {', '.join(KNOWLEDGE_SWITCHES)}"
            )
        return replace(
            self,
            topology_enabled=self.topology_enabled and TOPOLOGY_SWITCH not in switches,
            knowledge_enabled=self.knowledge_enabled and KNOWLEDGE_SWITCH not in switches,
        )

    def trace_summary(self) -> dict[str, object]:
        """Return what the run trace records about how the two stores were configured.

        The configuration, not what happened. "Topology was off" and "topology
        held nothing for that service" are different facts, and an ablation table
        that could not tell them apart would be unreadable.
        """
        return {
            "topology_enabled": self.topology_enabled,
            "knowledge_enabled": self.knowledge_enabled,
        }


def _switch(value: str | None) -> bool:
    """Return whether an environment value reads as on. Unset means on."""
    if value is None:
        return True
    text = value.strip().lower()
    return not text or text not in _FALSE_VALUES


__all__ = [
    "KNOWLEDGE_SWITCH",
    "KNOWLEDGE_SWITCHES",
    "TOPOLOGY_SWITCH",
    "KnowledgePolicy",
]
