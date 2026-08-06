"""The one capability in the set with no derivable rollback, deliberately shipped.

A cleared cache does not come back. The entries are gone, and the only thing
that repopulates them is traffic — which is not a plan, it is a hope with a
latency cost attached. So this generator returns ``None``, the request is
refused, and an operator who still wants it waives the requirement
explicitly and is audited for it.

It is in the shipped set precisely because of that. A waiver path nothing
exercises is a waiver path that is broken the first time somebody needs it,
during an incident, at the worst possible moment to discover it.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.remediation.models import RemediationAction, RollbackPlan, StateSnapshot

TOOL_NAME = "clear_cache"


@dataclass(frozen=True, slots=True)
class NoDerivablePlan:
    """Returns nothing, because nothing is what undoes a cache clear."""

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return ``None``: a cleared cache cannot be restored."""
        del action, before
        return None


generator = NoDerivablePlan()

__all__ = ["TOOL_NAME", "NoDerivablePlan", "generator"]
