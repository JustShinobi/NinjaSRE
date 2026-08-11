"""What would happen to an action of each risk class, in sentences.

The policy document answers "what are the rules". This answers the question an
operator actually asks before trusting a deployment with a cluster: *if
something of this kind came up right now, what would this thing do?* The
material for it already exists — the resolver, the bounds and the gate all
return their own explanation — and what was missing was the iteration over a set
of actions to ask about.

**The set is declared, not sampled.** ``REPRESENTATIVE_ACTIONS`` is one action
per risk class. A deployment on its first day has no decision history, and the
first day is exactly when somebody decides whether to let this act; an answer
that needed history would be blank at the only moment it mattered. Where history
does exist, the recorded-action preview complements this rather than replacing
it.

**The sentences are future tense, and the gate's are not.** ``Decision.reason``
is written for something that happened — "ran without asking", "was refused". A
reading of the current posture is about something that has not happened, and
rendering a past-tense sentence beside a hypothetical is how a screen ends up
being read as a log. So the sentence is composed here, from the same decision,
and the gate's own reason travels beside it as the detail.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.autonomy import (
    REPRESENTATIVE_ACTIONS,
    REPRESENTATIVE_RESOURCE_ID,
    RepresentativeAction,
)
from platform.autonomy.decision import Decision, Outcome
from platform.autonomy.risk import risk_class_of
from platform.autonomy.subjects import ProposedAction, Subject

#: How each outcome reads when it has not happened yet. One per member of
#: ``Outcome``, so a sixth outcome fails the lookup here rather than rendering
#: as an empty sentence on a screen somebody is trusting.
_SENTENCES: dict[Outcome, str] = {
    Outcome.EXECUTE: "would run on its own, without asking anybody.",
    Outcome.SIMULATE: (
        "would be permitted to run on its own, and would be simulated instead: this scope "
        "is in dry-run mode, so nothing is performed."
    ),
    Outcome.PROPOSE: "would be proposed for a person to run, and nothing would happen until they did.",
    Outcome.APPROVE: "would wait for a person's approval before anything happened.",
    Outcome.REFUSE: "would be refused outright, and no approval would let it through.",
}


@dataclass(frozen=True, slots=True)
class ClassOutlook:
    """What one risk class would meet under the posture as it stands."""

    risk_class: str
    capability: str
    resource_kind: str
    summary: str
    decision: Decision

    @property
    def outcome(self) -> str:
        """Return the decision this class would reach, as the API names it."""
        return self.decision.outcome.value

    @property
    def level(self) -> str:
        """Return the autonomy level this class resolves to."""
        return self.decision.resolution.level.value

    @property
    def refused_by(self) -> str:
        """Return the bound that decided it, or empty when none applied."""
        return self.decision.bound.value if self.decision.bound is not None else ""

    @property
    def dry_run(self) -> bool:
        """Return whether this scope is simulating rather than acting."""
        return self.decision.resolution.dry_run

    def describe(self) -> str:
        """Return the sentence the tab shows for this class.

        Leads with the class and what it means, because that is what the reader
        is matching their own situation against — not with the level, which is
        the answer rather than the question.
        """
        bound = f" The {self.refused_by} is what stops it." if self.refused_by else ""
        return f"{self.summary} It {_SENTENCES[self.decision.outcome]}{bound}"


def representative_action(declared: RepresentativeAction, *, team_node_id: str) -> ProposedAction:
    """Return the hypothetical action ``declared`` describes, for one team.

    ``has_rollback_plan`` is true because the question being asked is about the
    *policy*, and a missing rollback plan is a fact about a capability. Asking
    with one absent would report every class as needing approval and attribute
    it to the posture, which is the one wrong answer this tab must not give.
    """
    return ProposedAction(
        action_id=f"outlook-{declared.risk_class}",
        capability=declared.capability,
        subjects=(
            Subject(
                resource_id=REPRESENTATIVE_RESOURCE_ID,
                kind=declared.resource_kind,
                team_node_id=team_node_id,
            ),
        ),
        risk_class=risk_class_of(declared.risk_class),
        has_rollback_plan=True,
        team_node_id=team_node_id,
        intent="Reading the current posture, not proposing anything.",
    )


def representative_actions(*, team_node_id: str) -> tuple[ProposedAction, ...]:
    """Return one hypothetical action per risk class, least dangerous first."""
    return tuple(
        representative_action(declared, team_node_id=team_node_id)
        for declared in REPRESENTATIVE_ACTIONS
    )


def outlook_of(decisions: tuple[Decision, ...]) -> tuple[ClassOutlook, ...]:
    """Return the per-class reading ``decisions`` describes, in declared order.

    Raises:
        ValueError: ``decisions`` is not one per declared representative action.
    """
    if len(decisions) != len(REPRESENTATIVE_ACTIONS):
        raise ValueError(
            f"the outlook needs one decision per representative action; "
            f"expected {len(REPRESENTATIVE_ACTIONS)}, found {len(decisions)}"
        )
    return tuple(
        ClassOutlook(
            risk_class=declared.risk_class,
            capability=declared.capability,
            resource_kind=declared.resource_kind,
            summary=declared.summary,
            decision=decision,
        )
        for declared, decision in zip(REPRESENTATIVE_ACTIONS, decisions, strict=True)
    )


__all__ = [
    "ClassOutlook",
    "outlook_of",
    "representative_action",
    "representative_actions",
]
