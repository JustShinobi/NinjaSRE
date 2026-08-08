"""What is being changed, and what is being proposed about it.

Two values, both frozen, both carrying only what a decision is a function of.
Neither holds its own verdict: an action that could carry "permitted" would be
one a caller could construct as permitted, which is the property this whole
package exists to deny.

**An action names its subjects as a set, not one target.** Draining a node
touches every guest on it, and a decision that looked only at the node would be
permitting changes to resources whose rules it never read. Resolution takes the
least permissive level across them, and the explanation says which subject
supplied it.

**The risk class is on the action, not looked up here.** It comes from the
capability's declaration and is passed in already resolved, so the one place
"unclassified means critical" is decided is ``risk.risk_class_of`` — rather than
here, and again in the gate, and differently the third time.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from platform.autonomy.risk import RiskClass


@dataclass(frozen=True, slots=True)
class Subject:
    """One resource an action would change, and the facts a rule can match on.

    ``labels`` is the operator's own vocabulary — ``env=lab``, ``tier=backup`` —
    and is matched exactly rather than by pattern. A glob over labels would be a
    second selector language beside the resource pattern, and the failure mode
    of an over-broad label selector is the datastore holding the photographs.
    """

    resource_id: str
    kind: str = ""
    labels: Mapping[str, str] = field(default_factory=dict)
    team_node_id: str = ""

    def __post_init__(self) -> None:
        if not self.resource_id:
            raise ValueError(
                "A subject needs the resource it names. A subject scoped to nothing "
                "is a subject scoped to everything."
            )
        object.__setattr__(self, "labels", dict(self.labels))

    def has_labels(self, required: Mapping[str, str]) -> bool:
        """Return whether every label in ``required`` is present with that value."""
        return all(self.labels.get(name) == value for name, value in required.items())

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the audit trail and the explanation carry."""
        return {
            "resource_id": self.resource_id,
            "kind": self.kind,
            "labels": dict(self.labels),
            "team_node_id": self.team_node_id,
        }


@dataclass(frozen=True, slots=True)
class ProposedAction:
    """One change somebody or something wants made, before anybody decided.

    ``has_rollback_plan`` is a fact about the action rather than a preference:
    an action with no way back requires approval at every level, so a caller
    that could not answer it would be asking for a decision that cannot be made.
    """

    action_id: str
    capability: str
    subjects: tuple[Subject, ...]
    risk_class: RiskClass
    has_rollback_plan: bool = False
    requester: str = ""
    intent: str = ""
    run_id: str = ""
    team_node_id: str = ""
    #: The exact operation a person could run instead. What a proposal is *for*:
    #: "we would have restarted it" is a note, and a command is a handover.
    operation: str = ""

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("A proposed action needs an identifier.")
        if not self.capability:
            raise ValueError("A proposed action needs the capability that would perform it.")
        if not self.subjects:
            raise ValueError(
                "A proposed action needs at least one subject. An action with no subject "
                "cannot be resolved against any rule, and refusing it here is clearer "
                "than resolving it to the deployment default by accident."
            )

    @property
    def teams(self) -> tuple[str, ...]:
        """Return every team a subject belongs to, the action's own included."""
        found = {subject.team_node_id for subject in self.subjects if subject.team_node_id}
        if self.team_node_id:
            found.add(self.team_node_id)
        return tuple(sorted(found))

    def describe(self) -> str:
        """Return the one line a proposal, a listing and a refusal all show."""
        targets = ", ".join(subject.resource_id for subject in self.subjects)
        return f"{self.capability} on {targets}"

    def runnable(self) -> str:
        """Return the operation a person could run, described when none was given.

        Falls back to the description rather than to an empty string: a proposal
        whose "what a human could run" field is blank is a proposal that told
        nobody anything, and a sentence is worth more than nothing while a
        capability is still learning to render its own command.
        """
        return self.operation or self.describe()

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, complete enough to replay a decision from."""
        return {
            "action_id": self.action_id,
            "capability": self.capability,
            "subjects": [subject.to_record() for subject in self.subjects],
            "risk_class": self.risk_class.value,
            "has_rollback_plan": self.has_rollback_plan,
            "requester": self.requester,
            "intent": self.intent,
            "run_id": self.run_id,
            "team_node_id": self.team_node_id,
            "operation": self.runnable(),
        }


__all__ = [
    "ProposedAction",
    "Subject",
]
