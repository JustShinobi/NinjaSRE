"""The four things every remediation capability provides, and the map of them.

A capability that changes production is not one function. It is four, and the
split is not tidiness: each one is called at a different moment by a different
part of this package, and a capability missing any of them can reach a state
nobody can get out of.

``read_state``
    Called twice — before the action, to fingerprint what the approval is
    against and to enumerate the sub-targets, and after it, to verify. One
    reader for both, because two would eventually disagree about what "the
    state" is and the verification would compare two different things.

``apply``
    Called once, inside the sandbox, through the credential proxy, holding the
    target's lock. Returns a result per sub-target rather than a boolean,
    because partial success is the ordinary outcome of acting on a live system.

``rollback``
    Called *before* ``apply``, never after. That ordering is the whole control:
    a plan produced by the code that performs the action is a plan that does not
    exist when the action fails halfway.

``verify``
    Called after, on the state ``read_state`` read back. Returns the divergences
    between intent and reality, so "the API returned 200" is never mistaken for
    "the change took effect".

The protocols are declared here rather than in ``capabilities/`` because tier 2
may import tier 3 and not the other way round. A capability package implements
them and registers a bundle; nothing in this package imports a capability.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from platform.remediation.declaration import NOTHING_DECLARED, VerificationDeclaration
from platform.remediation.errors import UnknownRemediationCapability
from platform.remediation.models import (
    Divergence,
    RemediationAction,
    RollbackPlan,
    StateSnapshot,
    SubTargetResult,
)


@runtime_checkable
class StateReader(Protocol):
    """Reads what a target holds right now."""

    async def read(self, action: RemediationAction, *, at: datetime) -> StateSnapshot:
        """Return the target's observed state, or an unreadable snapshot.

        Never raises for an unreachable control plane. ``StateSnapshot.unreadable``
        is how "we could not tell" is expressed, and it is a different fact from
        an empty reading — one blocks the action and the other does not.
        """


@runtime_checkable
class ChangeApplier(Protocol):
    """Performs the change, one result per sub-target."""

    async def apply(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        environment: Any,
    ) -> tuple[SubTargetResult, ...]:
        """Return what happened to each piece of the target.

        ``before`` is the state the approval was granted against, so an applier
        that needs the prior value — a scale, a limit change — reads it from
        here rather than re-reading and racing whatever else is happening.

        ``environment`` names the sandbox this call is running inside and the
        proxy it reaches the control plane through. It is a parameter rather
        than something an applier looks up, which is what makes "no remediation
        runs outside an isolation profile" a property of this signature instead
        of a rule seven appliers each have to remember.
        """


@runtime_checkable
class PlanGenerator(Protocol):
    """Derives the plan that reverses one call, before the call happens."""

    def plan(self, action: RemediationAction, *, before: StateSnapshot) -> RollbackPlan | None:
        """Return the plan reversing ``action``, or ``None`` when none is derivable.

        ``None`` is a real answer, not a failure. A cache clear has no inverse,
        and saying so is what sends the request down the waiver path rather than
        producing a plan that would not work.
        """


@runtime_checkable
class OutcomeVerifier(Protocol):
    """Compares the state after the change against the state that was intended."""

    def verify(
        self,
        action: RemediationAction,
        *,
        before: StateSnapshot,
        after: StateSnapshot,
    ) -> tuple[Divergence, ...]:
        """Return every way the resulting state differs from the intended one."""


@dataclass(frozen=True, slots=True)
class RemediationComponents:
    """One capability's four components and its verification declaration.

    All five are required. An optional verifier would be omitted first and by
    exactly the capabilities whose results are hardest to check, which is the
    opposite of where the effort belongs — and the same is true of the
    declaration, which is why it has no default either.

    ``verifier`` and ``verification`` answer different questions and both are
    needed. The verifier compares the target's state against what the action
    *intended*, immediately, and catches "the API returned 200 and nothing
    changed". The declaration names the signals the *effect* appears in and how
    long to wait for them, and catches "the change took effect and the problem
    is still there". A system with only the first reports success for every
    remediation that did exactly what it was asked and did not help.
    """

    capability: str
    reader: StateReader
    applier: ChangeApplier
    generator: PlanGenerator
    verifier: OutcomeVerifier
    verification: VerificationDeclaration

    def __post_init__(self) -> None:
        if not self.capability:
            raise ValueError("Remediation components must name the capability they belong to.")


@dataclass(slots=True)
class ComponentRegistry:
    """Which capabilities this deployment can actually remediate with.

    A map rather than discovery. The set is small, it is security-relevant, and
    "which writes can this deployment perform" is a question an operator should
    be able to answer by reading one value rather than by importing a package
    tree and seeing what turns up.
    """

    components: dict[str, RemediationComponents] = field(default_factory=dict)

    def register(
        self,
        components: RemediationComponents,
        *,
        known_signals: Sequence[str] | None = None,
    ) -> ComponentRegistry:
        """Register ``components``, and return this registry so calls chain.

        ``known_signals`` is what this deployment's sources actually produce.
        When it is given, a capability naming a signal that is not in it raises
        ``UnknownVerificationSignal`` here rather than verifying against nothing
        forever. It is optional because a composition root that has not wired
        observation yet has no catalogue to check against, and refusing to
        register anything would make remediation depend on observation being
        configured first.
        """
        if known_signals is not None:
            components.verification.validate_against(known_signals)
        self.components[components.capability] = components
        return self

    def register_all(
        self,
        components: Iterable[RemediationComponents],
        *,
        known_signals: Sequence[str] | None = None,
    ) -> ComponentRegistry:
        """Register several bundles, and return this registry."""
        for bundle in components:
            self.register(bundle, known_signals=known_signals)
        return self

    def verification_of(self, capability: str) -> VerificationDeclaration:
        """Return how ``capability``'s effect is verified, or the nothing-declared one.

        Never raises. This is asked on the path of a decision about an action
        the deployment may not have components for, and an exception there would
        turn "we cannot verify that" — which is a policy question — into a
        failure of the decision itself.
        """
        found = self.components.get(capability)
        return NOTHING_DECLARED if found is None else found.verification

    def get(self, capability: str) -> RemediationComponents:
        """Return the components for ``capability``, or raise naming what is known."""
        found = self.components.get(capability)
        if found is None:
            raise UnknownRemediationCapability(capability, known=tuple(self.components))
        return found

    def has(self, capability: str) -> bool:
        """Return whether this deployment can remediate with ``capability``."""
        return capability in self.components

    def names(self) -> tuple[str, ...]:
        """Return every registered capability, in name order."""
        return tuple(sorted(self.components))

    def __len__(self) -> int:
        """Return how many capabilities are registered."""
        return len(self.components)


def registry_of(components: Mapping[str, RemediationComponents]) -> ComponentRegistry:
    """Return a registry holding ``components``, for a deployment wiring one up."""
    return ComponentRegistry(components=dict(components))


__all__ = [
    "ChangeApplier",
    "ComponentRegistry",
    "OutcomeVerifier",
    "PlanGenerator",
    "RemediationComponents",
    "StateReader",
    "registry_of",
]
