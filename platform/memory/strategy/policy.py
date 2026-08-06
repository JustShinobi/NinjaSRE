"""The switch that makes "playbooks help" a measurable claim.

A learning mechanism that has not been measured may not be claimed, and strategies
are the second learning mechanism in this package. The first one —
episodic recall — already has its two switches, so the temptation is to say
"strategies are part of memory" and reuse them. That would make the experiment
unrunnable.

The question this feature has to answer is not "does memory help" but "do
*playbooks* help, given the episodes were already there". Answering it needs a
baseline where the corpus is populated, recall is on, and only synthesis is off.
That is a third switch, and this is it.

It switches generation and retrieval together, deliberately. A run that could
retrieve strategies but not generate them would report a number that depends on
what happened to be in the cache when it started, which is not a measurement of
anything. "Strategies off" means the agent sees exactly what it would see in a
deployment where this feature does not exist.

Per-team resolution is a static default until the hierarchical configuration
service exists. ``for_team`` is the seam it will fill, and it is the same seam
``MemoryPolicy`` leaves.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from config.constants.memory import NINJASRE_MEMORY_STRATEGY_ENV

#: The axis the evaluation harness enumerates. A string rather than an enum
#: member, because an axis is identified in a results table and a report and both
#: of those are text.
STRATEGY_SWITCH = "memory_strategy"

STRATEGY_SWITCHES: tuple[str, ...] = (STRATEGY_SWITCH,)

#: Values that read as "off". Anything else is on, including a typo — a
#: mis-spelled value must not silently disable synthesis and leave an ablation
#: table reporting a result it never measured.
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class StrategyPolicy:
    """One team's strategy switch.

    Frozen, and ``without`` returns a new policy rather than mutating this one,
    so an ablation run cannot leave the switch flipped for the run after it —
    which is exactly the bug that would make the results table quietly wrong.
    """

    enabled: bool = True

    @classmethod
    def for_team(cls, *, enabled: bool = True) -> StrategyPolicy:
        """Return the policy for one team."""
        return cls(enabled=enabled)

    @classmethod
    def from_environment(cls) -> StrategyPolicy:
        """Return the policy an operator configured through the environment."""
        return cls(enabled=_switch(os.environ.get(NINJASRE_MEMORY_STRATEGY_ENV)))

    @classmethod
    def disabled(cls) -> StrategyPolicy:
        """Return the policy the episodes-only baseline runs under."""
        return cls(enabled=False)

    def without(self, *switches: str) -> StrategyPolicy:
        """Return this policy with ``switches`` turned off.

        Raises on a switch nobody defined. An ablation that silently ignored an
        unknown axis would publish a table saying it measured something it never
        varied, which is worse than not measuring it at all.
        """
        unknown = set(switches) - set(STRATEGY_SWITCHES)
        if unknown:
            raise ValueError(
                f"unknown strategy switch(es) {', '.join(sorted(unknown))}; "
                f"expected one of {', '.join(STRATEGY_SWITCHES)}"
            )
        return replace(self, enabled=self.enabled and STRATEGY_SWITCH not in switches)

    def trace_summary(self) -> dict[str, object]:
        """Return what the run trace records about how strategies were configured.

        The configuration, not what happened. "Strategies were off" and "no
        playbook existed yet" are different facts, and an ablation table that
        could not tell them apart would be unreadable.
        """
        return {"memory_strategy_enabled": self.enabled}


def _switch(value: str | None) -> bool:
    """Return whether an environment value reads as on. Unset means on."""
    if value is None:
        return True
    text = value.strip().lower()
    return not text or text not in _FALSE_VALUES


__all__ = [
    "STRATEGY_SWITCH",
    "STRATEGY_SWITCHES",
    "StrategyPolicy",
]
