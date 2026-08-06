"""The undo: derived first, checked before it is applied, honest about failing.

Three modules and one ordering that is the whole point of them. ``generator``
runs *before* the action and refuses when there is nothing to write down;
``verification`` runs before the plan is applied and refuses when the target has
moved; ``executor`` applies it and raises rather than reporting a rollback that
did not roll anything back.

Read in the other direction the package is a claim: nothing above
``read_sensitive`` executes in this system without something in here having
produced a plan for it first.
"""

from __future__ import annotations

from platform.remediation.rollback.executor import (
    RollbackExecutor,
    RollbackResult,
    StepRunner,
)
from platform.remediation.rollback.generator import PlanFactory, RollbackWaiver
from platform.remediation.rollback.verification import MatchReport, check, require_match

__all__ = [
    "MatchReport",
    "PlanFactory",
    "RollbackExecutor",
    "RollbackResult",
    "RollbackWaiver",
    "StepRunner",
    "check",
    "require_match",
]
