"""The two switches that make "memory helps" a measurable claim rather than a slogan.

Article VII forbids claiming a learning mechanism that has not been measured, and
the only honest way to measure this one is to run the same scenarios with it and
without it. That requires a switch, and it requires the switch to be somewhere
other than in a comment saying which lines to delete.

Reading and writing switch **separately**, and that is the interesting part. The
ablation worth running is a populated corpus the agent is not allowed to consult:
it isolates recall's contribution while leaving the corpus intact for the run
after. Turning both off is the pre-memory baseline, and the identity it has to
satisfy — an investigation otherwise unchanged — is what makes the comparison a
comparison rather than two different systems.

Turning memory off means the hooks are not installed at all, not that they are
installed and do nothing. A no-op hook still runs, still appears in the trace,
and still perturbs the ordering the trajectory scorer reads; "off" has to be the
same code path a deployment without memory takes.

Per-team resolution is a static default until the hierarchical configuration
service exists. ``for_team`` is the seam it will fill.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from config.constants.memory import NINJASRE_MEMORY_READ_ENV, NINJASRE_MEMORY_WRITE_ENV

#: The names the evaluation harness enumerates as ablation axes. Strings rather
#: than an enum, because an axis is identified in a results table and a report
#: and both of those are text.
MEMORY_READ_SWITCH = "memory_read"
MEMORY_WRITE_SWITCH = "memory_write"

MEMORY_SWITCHES: tuple[str, ...] = (MEMORY_READ_SWITCH, MEMORY_WRITE_SWITCH)

#: Values that read as "off" in an environment variable. Anything else is on,
#: including a typo — a mis-spelled value must not silently disable memory and
#: leave an ablation table reporting a result it never measured.
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """One team's memory switches.

    Frozen. ``without`` returns a new policy rather than mutating this one, so an
    ablation run cannot leave a switch flipped for the run after it — which is
    exactly the bug that would make the table quietly wrong.
    """

    read_enabled: bool = True
    write_enabled: bool = True

    @property
    def enabled(self) -> bool:
        """Return whether memory does anything at all under this policy."""
        return self.read_enabled or self.write_enabled

    @classmethod
    def for_team(cls, *, read_enabled: bool = True, write_enabled: bool = True) -> MemoryPolicy:
        """Return the policy for one team.

        The seam the configuration service fills. Until it exists every team
        resolves to what the caller states, which is the honest version of
        "per-team" before there is anywhere to store a per-team value.
        """
        return cls(read_enabled=read_enabled, write_enabled=write_enabled)

    @classmethod
    def from_environment(cls) -> MemoryPolicy:
        """Return the policy an operator configured through the environment."""
        return cls(
            read_enabled=_switch(os.environ.get(NINJASRE_MEMORY_READ_ENV)),
            write_enabled=_switch(os.environ.get(NINJASRE_MEMORY_WRITE_ENV)),
        )

    @classmethod
    def disabled(cls) -> MemoryPolicy:
        """Return the policy the pre-memory baseline runs under."""
        return cls(read_enabled=False, write_enabled=False)

    def without(self, *switches: str) -> MemoryPolicy:
        """Return this policy with ``switches`` turned off.

        Raises on a switch nobody defined. An ablation that silently ignored an
        unknown axis would publish a table saying it measured something it never
        varied, which is worse than not measuring it at all.
        """
        unknown = set(switches) - set(MEMORY_SWITCHES)
        if unknown:
            raise ValueError(
                f"unknown memory switch(es) {', '.join(sorted(unknown))}; "
                f"expected one of {', '.join(MEMORY_SWITCHES)}"
            )
        return replace(
            self,
            read_enabled=self.read_enabled and MEMORY_READ_SWITCH not in switches,
            write_enabled=self.write_enabled and MEMORY_WRITE_SWITCH not in switches,
        )

    def trace_summary(self) -> dict[str, object]:
        """Return what the run trace records about how memory was configured.

        The configuration, not what happened. "Recall was off" and "recall found
        nothing" are different facts, and an ablation table that could not tell
        them apart would be unreadable.
        """
        return {
            "memory_read_enabled": self.read_enabled,
            "memory_write_enabled": self.write_enabled,
        }


def _switch(value: str | None) -> bool:
    """Return whether an environment value reads as on. Unset means on."""
    if value is None:
        return True
    text = value.strip().lower()
    return not text or text not in _FALSE_VALUES


__all__ = [
    "MEMORY_READ_SWITCH",
    "MEMORY_SWITCHES",
    "MEMORY_WRITE_SWITCH",
    "MemoryPolicy",
]
