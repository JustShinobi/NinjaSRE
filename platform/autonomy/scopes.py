"""Where a rule applies, and which of two applicable rules is the more specific.

Seven scope kinds, ordered. The order is the precedence and it is declared in
``config.constants.autonomy`` rather than derived from the fields a scope
happens to set, because precedence is a promise to an operator and a promise
that changes when somebody adds a field is not one.

A label selector sits above a resource kind because it is a narrower statement
about the same population, and below an individual resource because naming one
machine is the narrowest thing anybody can say about it. Capability × resource
is the top: "restarting *this* container" is more specific than either half.

**Matching is exact, never a pattern.** A glob over resource identifiers reads
well and is one character away from matching everything, and the population this
selects is the one an over-broad rule executes against unattended. An operator
who wants a family of resources uses a label, which they control and which the
estate already carries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from config.constants.autonomy import (
    AUTONOMY_SCOPE_CAPABILITY,
    AUTONOMY_SCOPE_CAPABILITY_RESOURCE,
    AUTONOMY_SCOPE_DEPLOYMENT,
    AUTONOMY_SCOPE_KINDS,
    AUTONOMY_SCOPE_LABELS,
    AUTONOMY_SCOPE_RESOURCE,
    AUTONOMY_SCOPE_RESOURCE_KIND,
    AUTONOMY_SCOPE_TEAM,
)
from platform.autonomy.subjects import ProposedAction, Subject


class ScopeKind(StrEnum):
    """The seven places a level may be set, least to most specific."""

    DEPLOYMENT = AUTONOMY_SCOPE_DEPLOYMENT
    TEAM = AUTONOMY_SCOPE_TEAM
    RESOURCE_KIND = AUTONOMY_SCOPE_RESOURCE_KIND
    LABELS = AUTONOMY_SCOPE_LABELS
    CAPABILITY = AUTONOMY_SCOPE_CAPABILITY
    RESOURCE = AUTONOMY_SCOPE_RESOURCE
    CAPABILITY_RESOURCE = AUTONOMY_SCOPE_CAPABILITY_RESOURCE

    @property
    def specificity(self) -> int:
        """Return this kind's position in the precedence order."""
        return AUTONOMY_SCOPE_KINDS.index(self.value)


@dataclass(frozen=True, slots=True)
class PolicyScope:
    """What a rule is about: a kind, and the fields that kind needs.

    One type rather than seven, because resolution walks a single list and a
    seven-way union would put the walk's shape in every caller. The kind decides
    which fields are read; ``__post_init__`` refuses a scope whose kind and
    fields disagree, so a rule that would silently apply to everything cannot be
    constructed at all.
    """

    kind: ScopeKind
    team_node_id: str = ""
    resource_kind: str = ""
    resource_id: str = ""
    capability: str = ""
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "labels", dict(self.labels))
        for name in _REQUIRED_FIELDS[self.kind]:
            if not getattr(self, name):
                raise ValueError(
                    f"a {self.kind.value} scope needs {name}; without it the rule applies "
                    f"to everything, which is not what naming a scope means"
                )

    @property
    def specificity(self) -> int:
        """Return where this scope sits in the precedence order."""
        return self.kind.specificity

    @property
    def identity(self) -> str:
        """Return the stable identifier a rule is named and tie-broken by.

        Derived from the scope rather than assigned, so the same scope written
        twice in two documents produces the same name — which is what makes a
        preview able to say "this rule changed" rather than "one rule went and
        another arrived".
        """
        labels = ",".join(f"{name}={value}" for name, value in sorted(self.labels.items()))
        parts = (
            self.kind.value,
            self.team_node_id,
            self.resource_kind,
            self.resource_id,
            self.capability,
            labels,
        )
        return ":".join(parts)

    def matches(self, action: ProposedAction, subject: Subject) -> bool:
        """Return whether this scope covers ``subject`` under ``action``."""
        if self.kind is ScopeKind.DEPLOYMENT:
            return True
        if self.kind is ScopeKind.TEAM:
            return self.team_node_id in (subject.team_node_id, action.team_node_id)
        if self.kind is ScopeKind.RESOURCE_KIND:
            return subject.kind == self.resource_kind
        if self.kind is ScopeKind.LABELS:
            return subject.has_labels(self.labels)
        if self.kind is ScopeKind.CAPABILITY:
            return action.capability == self.capability
        if self.kind is ScopeKind.RESOURCE:
            return subject.resource_id == self.resource_id
        return action.capability == self.capability and subject.resource_id == self.resource_id

    def describe(self) -> str:
        """Return the phrase an explanation reads with, in an operator's words."""
        if self.kind is ScopeKind.DEPLOYMENT:
            return "the whole deployment"
        if self.kind is ScopeKind.TEAM:
            return f"team {self.team_node_id}"
        if self.kind is ScopeKind.RESOURCE_KIND:
            return f"every {self.resource_kind}"
        if self.kind is ScopeKind.LABELS:
            listed = ", ".join(f"{name}={value}" for name, value in sorted(self.labels.items()))
            return f"anything labelled {listed}"
        if self.kind is ScopeKind.CAPABILITY:
            return f"{self.capability} anywhere"
        if self.kind is ScopeKind.RESOURCE:
            return f"the resource {self.resource_id}"
        return f"{self.capability} on {self.resource_id}"

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which is also the exported document's form."""
        record: dict[str, Any] = {"kind": self.kind.value}
        for name in ("team_node_id", "resource_kind", "resource_id", "capability"):
            value = getattr(self, name)
            if value:
                record[name] = value
        if self.labels:
            record["labels"] = dict(self.labels)
        return record


#: What each kind cannot be without. ``deployment`` needs nothing — it is the
#: statement "everywhere", which is a decision rather than an omission.
_REQUIRED_FIELDS: dict[ScopeKind, tuple[str, ...]] = {
    ScopeKind.DEPLOYMENT: (),
    ScopeKind.TEAM: ("team_node_id",),
    ScopeKind.RESOURCE_KIND: ("resource_kind",),
    ScopeKind.LABELS: ("labels",),
    ScopeKind.CAPABILITY: ("capability",),
    ScopeKind.RESOURCE: ("resource_id",),
    ScopeKind.CAPABILITY_RESOURCE: ("capability", "resource_id"),
}


__all__ = [
    "PolicyScope",
    "ScopeKind",
]
