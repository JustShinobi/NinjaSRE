"""The operator's own control plane: read as intent, never written to.

Where somebody runs a declarative control plane over the same infrastructure —
a repository with an inventory, a validate/plan/apply cycle, and its own state —
that repository holds something the hypervisor API cannot report: what is
*supposed* to be true. Which guests should be running, what role each node has,
which services matter. That is exactly the missing half of half the detectors in
the shipped set: "a guest stopped that was expected running" needs somebody to
have expected it.

So it is read. And it is never written.

**A second writer is how drift becomes an outage.** The repository's apply path
is the one the operator tests, reviews and rolls back. A system that also wrote
to the live host would produce a host that disagrees with its own declaration,
and the next apply would revert the fix without anybody connecting the two
events. The failure mode is not "the change was lost" — it is "the change was
lost three days later, silently, during an unrelated deployment".

**A remediation whose correct form is a change to that repository is proposed as
one.** Not applied to the host with a note. The proposal names the file, says
what would change in it, and stops — because the operator's own pipeline is the
thing that should carry it, and handing it over is the whole point.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from config.constants.guardian import DECLARED_INTENT_READ_ONLY_REASON


@dataclass(frozen=True, slots=True)
class DeclaredResource:
    """One resource as the operator's control plane declares it should be.

    Deliberately a small, common shape rather than any particular tool's
    format. What every declarative inventory of a hypervisor estate has is a
    name, whether it is meant to be running, and which of its properties the
    repository owns — and the third is the field that decides what may be
    written.
    """

    native_id: str
    #: Whether this resource is declared as one that should be running. ``None``
    #: means the inventory declares the resource without declaring its state,
    #: which is a real and common case and must not read as "should be stopped".
    expected_running: bool | None = None
    role: str = ""
    #: The properties this repository owns. A remediation touching one of these
    #: is a remediation that belongs in the repository.
    owns: tuple[str, ...] = ()
    labels: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeclaredIntent:
    """Everything the operator's control plane says about the estate.

    Held as a value rather than reached through a client, because reading a
    repository is not this package's business — a caller hands over what it
    parsed, and what happens here is the comparison.
    """

    source: str = ""
    resources: tuple[DeclaredResource, ...] = ()

    @property
    def available(self) -> bool:
        """Return whether there is a declaration to compare against at all."""
        return bool(self.source and self.resources)

    def declared(self, native_id: str) -> DeclaredResource | None:
        """Return what the control plane says about ``native_id``, or ``None``."""
        for resource in self.resources:
            if resource.native_id == native_id:
                return resource
        return None

    def expects_running(self, native_id: str) -> bool:
        """Return whether ``native_id`` is declared as something that should be running.

        ``False`` for a resource the inventory does not mention, which is
        correct rather than cautious: a guest nobody declared is a guest whose
        being stopped is not a deviation from anything.
        """
        declared = self.declared(native_id)
        return bool(declared is not None and declared.expected_running)

    def owns_property(self, native_id: str, name: str) -> bool:
        """Return whether the control plane owns ``name`` on ``native_id``."""
        declared = self.declared(native_id)
        return declared is not None and name in declared.owns


@dataclass(frozen=True, slots=True)
class DeclarativeProposal:
    """A remediation redirected into the operator's own pipeline.

    Carries what would have been done and where it should go instead, which is
    the minimum an operator needs to act on it without going back to the
    incident.
    """

    native_id: str
    property_name: str
    intended_change: str
    source: str

    def describe(self) -> str:
        """Return what the proposal says in place of an action."""
        return (
            f"{self.intended_change} would change {self.property_name} on {self.native_id}, "
            f"which is owned by the declarative control plane at {self.source}. "
            f"{DECLARED_INTENT_READ_ONLY_REASON}. Nothing has been written to the live "
            f"host: applying this here would leave the host disagreeing with its own "
            f"declaration, and the next apply would revert it without anybody connecting "
            f"the two events."
        )

    def to_record(self) -> dict[str, Any]:
        """Return the document the proposal is stored and rendered as."""
        return {
            "native_id": self.native_id,
            "property": self.property_name,
            "intended_change": self.intended_change,
            "source": self.source,
            "apply_here": False,
            "description": self.describe(),
        }


def redirect_if_declared(
    intent: DeclaredIntent,
    *,
    native_id: str,
    property_name: str,
    intended_change: str,
) -> DeclarativeProposal | None:
    """Return the proposal to make instead of acting, or ``None`` to act normally.

    ``None`` is the ordinary answer. Most remediations touch runtime state that
    no repository owns — starting a guest, clearing a lock, retrying a backup —
    and redirecting those would make the control plane's existence a reason the
    deployment can do nothing.
    """
    if not intent.available or not intent.owns_property(native_id, property_name):
        return None
    return DeclarativeProposal(
        native_id=native_id,
        property_name=property_name,
        intended_change=intended_change,
        source=intent.source,
    )


def unexpectedly_stopped(
    intent: DeclaredIntent, *, running: Iterable[str], known: Iterable[str]
) -> tuple[str, ...]:
    """Return the guests the control plane expects running that are not.

    The reading a hypervisor API cannot produce on its own: it knows what is
    running and has no opinion about what should be. ``known`` bounds the answer
    to guests this deployment can actually see, so an inventory entry for a
    guest on a cluster nobody connected is not reported as stopped.
    """
    live = set(running)
    visible = set(known)
    return tuple(
        sorted(
            resource.native_id
            for resource in intent.resources
            if resource.expected_running
            and resource.native_id in visible
            and resource.native_id not in live
        )
    )


__all__ = [
    "DeclarativeProposal",
    "DeclaredIntent",
    "DeclaredResource",
    "redirect_if_declared",
    "unexpectedly_stopped",
]
