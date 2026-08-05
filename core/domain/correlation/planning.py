"""The shortlist the loop is handed, and the sentence explaining it.

A plan is advisory. That is the whole design decision, and it is written into
the type rather than left to the caller: ``binding`` is computed from the
scores, so a plan assembled from weak matches cannot be handed to a conclusion
policy that would hold the run open until every entry had been called.

The alternative — a binding plan — is worse in exactly the case that matters.
When the incident is not what the alert suggested, a binding plan spends the
budget confirming that the alert was misleading.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.investigation import PLAN_CONFIDENCE_FLOOR


@dataclass(frozen=True, slots=True)
class PlannedAction:
    """One capability the plan shortlisted, with the score that put it there."""

    capability: str
    score: float = 0.0
    rationale: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.capability.strip():
            raise ValueError("a planned action must name a capability")

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this action."""
        return {
            "capability": self.capability,
            "score": self.score,
            "rationale": list(self.rationale),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> PlannedAction:
        """Return the action a stored record describes."""
        return cls(
            capability=str(record["capability"]),
            score=float(record.get("score", 0.0)),
            rationale=tuple(str(item) for item in record.get("rationale") or ()),
        )


@dataclass(frozen=True, slots=True)
class EvidencePlan:
    """What the planning stage decided, and why.

    ``rationale`` is written prose rather than the per-action reasons. Someone
    reading the trace after a bad investigation wants one paragraph saying what
    the plan was trying to establish, not fourteen lines of arithmetic.
    """

    actions: tuple[PlannedAction, ...] = ()
    rationale: str = ""
    excluded_note: str = ""

    @property
    def capabilities(self) -> tuple[str, ...]:
        """Return the shortlisted capability names, highest score first."""
        return tuple(action.capability for action in self.actions)

    @property
    def top_score(self) -> float:
        """Return the best score in the plan, or zero when it is empty."""
        return max((action.score for action in self.actions), default=0.0)

    @property
    def binding(self) -> bool:
        """Return whether the loop should be held to this plan.

        Empty or weak means no. The whole advisory rule in one property: the loop falls back to
        its own relevance ranking rather than being pinned to a shortlist that
        scored well only because nothing else did.
        """
        return bool(self.actions) and self.top_score >= PLAN_CONFIDENCE_FLOOR

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this plan."""
        return {
            "actions": [action.to_record() for action in self.actions],
            "rationale": self.rationale,
            "excluded_note": self.excluded_note,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> EvidencePlan:
        """Return the plan a stored record describes."""
        return cls(
            actions=tuple(PlannedAction.from_record(item) for item in record.get("actions") or ()),
            rationale=str(record.get("rationale", "")),
            excluded_note=str(record.get("excluded_note", "")),
        )


def plan_from(actions: Sequence[PlannedAction], *, rationale: str = "") -> EvidencePlan:
    """Return a plan over ``actions``, ordered by score with ties broken by name.

    The tiebreak is what keeps two runs of the same scenario producing the same
    shortlist. Without it, a rebuild that reordered the catalogue would reorder
    the plan, and a trajectory comparison would be reading noise.
    """
    ordered = sorted(actions, key=lambda action: (-action.score, action.capability))
    return EvidencePlan(actions=tuple(ordered), rationale=rationale)


#: The plan a stage produces when it has nothing to shortlist.
EMPTY_PLAN: EvidencePlan = EvidencePlan()

__all__ = [
    "EMPTY_PLAN",
    "EvidencePlan",
    "PlannedAction",
    "plan_from",
]
