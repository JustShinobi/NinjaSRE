"""What a hypervisor write has to say about itself before it may be registered.

Six things, and none of them has a default: the risk class it is classified at,
the preconditions it will be checked against, its rollback plan or an explicit
statement that it has none, the signals its effect appears in, how long to wait
before those signals mean anything, and the Proxmox privileges a token needs to
perform it.

**The failure is at registration, not at runtime.** A declaration that is missing
any of them cannot be constructed, so a capability without one is an import
error rather than a surprise during an incident. That is the strongest form the
requirement takes: nothing that reaches the registry can be incomplete, because
nothing incomplete can be built.

**The class comes from the table, never from here.** ``risk_class`` is a property
that reads the risk table, so a capability cannot declare a class the table does
not give it and the two cannot drift into disagreement. A capability the table
does not classify fails to construct.

**The endpoint is declared, and it is swept.** Every declaration names the exact
Proxmox path it writes, which is what lets one test assert over the whole
registry that nothing fences a node, forces quorum, alters corosync, restarts a
node service, or writes a node's network configuration. A capability added in a
prohibited category fails the suite rather than shipping.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from capabilities.tools.remediation.proxmox import risk
from capabilities.tools.remediation.proxmox.preconditions import Precondition
from integrations.proxmox.privileges import RequiredPrivilege
from platform.autonomy.risk import RiskClass
from platform.remediation.declaration import VerificationDeclaration
from platform.remediation.errors import RemediationError
from platform.remediation.models import RemediationAction, StateSnapshot


class RegistrationRefused(RemediationError):
    """A capability declared less than a hypervisor write has to declare.

    Raised while the declaration is built, which is import time, so the deployment
    fails to start rather than discovering the gap while somebody is waiting for
    an incident to close.
    """

    def __init__(self, capability: str, missing: str) -> None:
        super().__init__(
            f"{capability or 'an unnamed hypervisor write'} cannot be registered: {missing} "
            f"Every write against a hypervisor declares its risk class, its preconditions, its "
            f"rollback plan or the explicit absence of one, its verification signals, its "
            f"settle period, and the privileges it needs."
        )
        self.capability = capability
        self.missing = missing


class WriteCategory(StrEnum):
    """Which family of write this is, which decides what a fresh reading has to hold."""

    GUEST_LIFECYCLE = "guest_lifecycle"
    MOVEMENT = "movement"
    HIGH_AVAILABILITY = "high_availability"
    STORAGE = "storage"
    BACKUP = "backup"
    REPLICATION = "replication"


@dataclass(frozen=True, slots=True)
class RollbackDeclaration:
    """How this write is undone, or the stated reason it cannot be.

    Exactly one of the two. A declaration with both describes something that is
    not the case, and one with neither is a capability nobody finished — which is
    the state this type exists to make unbuildable.
    """

    summary: str = ""
    steps: tuple[str, ...] = ()
    reversible: bool = True
    #: Why no plan exists. Required when, and only when, there is no summary.
    absent_because: str = ""
    #: The capability that performs the undo. Rarely the declaring one: a start
    #: is undone by a shutdown and a suspend by a resume, and a step naming the
    #: capability that made the change would replay the change.
    performed_by: str = ""

    def __post_init__(self) -> None:
        if self.summary.strip() and self.absent_because.strip():
            raise ValueError(
                "A rollback declaration says how the action is undone or why it cannot be. "
                "Saying both describes something that is not the case."
            )
        if self.summary.strip() and not self.steps:
            raise ValueError(
                f"{self.summary!r} promises an undo and lists no steps. A summary with no "
                f"steps is a plan nobody can run at three in the morning."
            )

    @classmethod
    def none(cls, reason: str) -> RollbackDeclaration:
        """Return the declaration that this write has no undo, carrying the reason."""
        if not reason.strip():
            raise ValueError(
                "A capability with no rollback has to say why. The reason is what makes it a "
                "decision somebody made rather than a field nobody filled in."
            )
        return cls(absent_because=reason, reversible=False)

    @property
    def derivable(self) -> bool:
        """Return whether a plan exists to derive at all."""
        return bool(self.summary.strip())

    def describe(self) -> str:
        """Return the sentence a proposal shows about undoing this."""
        return self.summary if self.derivable else f"No rollback: {self.absent_because}"


#: What turns an action into the state it intends to leave behind. The same
#: mapping is what the control plane is asked for and what the verifier compares
#: the result against, so "the API returned 200" can never stand in for "the
#: target holds what the action asked for".
type IntentOf = Callable[[RemediationAction, StateSnapshot], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ProxmoxRemediation:
    """Everything one hypervisor write declares, checked as it is built."""

    capability: str
    category: WriteCategory
    #: The Proxmox path this writes, with ``{node}`` where the node name goes.
    #: Declared rather than derived so the prohibition sweep has something to
    #: read that is not the implementation.
    endpoint: str
    method: str
    preconditions: tuple[Precondition, ...]
    rollback: RollbackDeclaration
    verification: VerificationDeclaration
    privileges: tuple[RequiredPrivilege, ...]
    #: The snapshot fields this action is about — what the reader records, what
    #: the rollback restores, and what the verifier compares.
    fields: tuple[str, ...]
    #: The subset of ``fields`` that says the target is still the thing that was
    #: approved. A subset rather than all of them, because a running guest's
    #: uptime changes every second and a check that compared it would refuse
    #: every action against every running guest.
    identity_fields: tuple[str, ...]
    intent_of: IntentOf
    #: Whether performing this needs the cluster configuration filesystem to be
    #: writable. Almost everything on a Proxmox node does, because a guest's own
    #: state lives in ``/etc/pve``.
    writes_configuration: bool
    #: Whether performing this would mean treating an unreachable node as dead.
    assumes_node_is_dead: bool = False
    #: What a person would run instead, as a shell command. A proposal that says
    #: "we would have migrated it" is a note; one that carries the command is a
    #: handover.
    operation: str = ""
    arguments: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.capability.strip():
            raise RegistrationRefused("", "it does not name the capability it belongs to.")
        try:
            risk.row_for(self.capability)
        except KeyError as unclassified:
            raise RegistrationRefused(
                self.capability,
                "the risk table does not classify it, so nobody has assessed how dangerous it is.",
            ) from unclassified
        if not self.endpoint.strip() or not self.method.strip():
            raise RegistrationRefused(
                self.capability, "it does not name the endpoint and method it writes."
            )
        forbidden = risk.prohibition_for(self.endpoint)
        if forbidden is not None:
            raise RegistrationRefused(
                self.capability,
                f"{self.endpoint} is a {forbidden.name} operation, and {forbidden.why}.",
            )
        if not self.preconditions:
            raise RegistrationRefused(
                self.capability,
                "it declares no preconditions. Every write is checked against a fresh reading "
                "before it runs, and a write with nothing to check is one that acts on a "
                "picture taken minutes ago.",
            )
        if not self.rollback.derivable and not self.rollback.absent_because.strip():
            raise RegistrationRefused(
                self.capability, "it declares neither a rollback plan nor a reason it has none."
            )
        if not self.verification.verifiable and not self.verification.reason.strip():
            raise RegistrationRefused(
                self.capability,
                "it declares neither the signals its effect appears in nor a reason there are "
                "none.",
            )
        if self.verification.verifiable and not self.verification.settle_seconds:
            raise RegistrationRefused(
                self.capability,
                "it declares signals and no settle period, so it would verify against the "
                "reading the detector already fired on.",
            )
        if not self.privileges:
            raise RegistrationRefused(
                self.capability,
                "it names no Proxmox privilege, so nothing can tell an operator whether the "
                "token they pasted would let it run.",
            )
        if not self.fields:
            raise RegistrationRefused(
                self.capability,
                "it names no state fields, so there is nothing to snapshot, nothing to restore "
                "and nothing to verify against.",
            )
        outside = sorted(set(self.identity_fields) - set(self.fields))
        if not self.identity_fields or outside:
            raise RegistrationRefused(
                self.capability,
                f"its identity fields {outside or 'are empty'} are not part of what it reads, "
                f"so 'the target changed' would be decided against something never recorded.",
            )

    @property
    def risk_class(self) -> RiskClass:
        """Return the class the risk table gives this capability."""
        return risk.class_of(self.capability)

    @property
    def row(self) -> risk.RiskRow:
        """Return the capability's whole row, reasoning included."""
        return risk.row_for(self.capability)

    def path_for(self, node: str) -> str:
        """Return the declared endpoint with ``node`` substituted in."""
        return self.endpoint.replace("{node}", node)

    def describe(self) -> str:
        """Return the paragraph a proposal or a review shows about this write."""
        return (
            f"{self.capability} [{self.risk_class.value}] {self.method} {self.endpoint}\n"
            f"  preconditions: {', '.join(name.value for name in self.preconditions)}\n"
            f"  rollback: {self.rollback.describe()}\n"
            f"  verification: {self.verification.describe()}\n"
            f"  privileges: {', '.join(privilege.describe() for privilege in self.privileges)}"
        )


def declarations_of(declared: Sequence[ProxmoxRemediation]) -> dict[str, ProxmoxRemediation]:
    """Return ``declared`` keyed by capability, refusing two with one name."""
    found: dict[str, ProxmoxRemediation] = {}
    for declaration in declared:
        if declaration.capability in found:
            raise RegistrationRefused(
                declaration.capability,
                "two declarations carry that name, so which one runs would depend on import order.",
            )
        found[declaration.capability] = declaration
    return found


__all__ = [
    "IntentOf",
    "ProxmoxRemediation",
    "RegistrationRefused",
    "RollbackDeclaration",
    "WriteCategory",
    "declarations_of",
]
