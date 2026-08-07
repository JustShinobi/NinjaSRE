"""Running an integration's checks, and holding what they found.

The runner is small on purpose. Everything interesting about verification is in
what a vendor's verifier chooses to probe and in how the result is worded; the
part that walks a list and gathers results should be boring, and boring is what
lets it be the same for all eighty-five.

Two decisions here are load-bearing.

**Connectivity gates the permission probes.** A credential the vendor rejects
makes every permission *unchecked*, not denied. The alternative — running the
probes anyway and reporting eight denials — sends an operator to re-issue eight
scopes on a key that simply needs replacing, and the report that caused it was
technically accurate about every one of them.

**A verifier must say what its connectivity probe is.** FR-011 allows a vendor
with no verification endpoint to use its cheapest read capability instead, and
allows it *on condition that the substitution is documented*. An empty
description is how that condition quietly stops holding, so it is refused at
construction rather than reviewed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from integrations._verification.permissions import (
    PermissionOutcome,
    PermissionProbe,
    ProbeState,
)


@dataclass(frozen=True, slots=True)
class Connectivity:
    """Whether the integration reached its vendor, and what it was told if not.

    ``detail`` is the operator-facing half. "401 Unauthorized" tells them to
    re-issue the key; "could not reach the host" tells them to look at egress;
    "no credential is configured for this team" tells them to run setup. All
    three are failures, and collapsing them loses the only part that decides
    what to do next.
    """

    reachable: bool
    detail: str = ""
    status_code: int | None = None

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a CLI or console renders."""
        return {
            "reachable": self.reachable,
            "detail": self.detail,
            "status_code": self.status_code,
        }


@runtime_checkable
class IntegrationVerifier(Protocol):
    """One vendor's connectivity and permission checks (FR-009)."""

    @property
    def integration(self) -> str:
        """Return the integration this verifier checks."""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call was chosen."""

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""

    async def connect(self, transport: Any, context: Any) -> Connectivity:
        """Make the cheapest authenticated call and report whether it worked."""


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """What one integration's verification established, in full."""

    integration: str
    connectivity: Connectivity
    permissions: tuple[PermissionOutcome, ...] = ()
    probe_description: str = ""

    @property
    def ok(self) -> bool:
        """Return whether the integration is usable as configured.

        Reachable and nothing denied. An inconclusive probe does not fail the
        report — nothing was established, and failing on "we could not tell"
        would make a rate-limited verification run look like a broken
        credential.
        """
        return self.connectivity.reachable and not any(
            outcome.denied for outcome in self.permissions
        )

    @property
    def missing_permissions(self) -> tuple[str, ...]:
        """Return the permissions the vendor confirmed are absent."""
        return tuple(outcome.permission.name for outcome in self.permissions if outcome.denied)

    @property
    def unchecked_permissions(self) -> tuple[str, ...]:
        """Return the permissions nothing was established about."""
        return tuple(
            outcome.permission.name
            for outcome in self.permissions
            if outcome.state in {ProbeState.INCONCLUSIVE, ProbeState.UNCHECKED}
        )

    @property
    def affected_capabilities(self) -> tuple[str, ...]:
        """Return the capabilities that cannot run as this credential stands."""
        affected = {
            capability
            for outcome in self.permissions
            if outcome.denied
            for capability in outcome.permission.capabilities
        }
        return tuple(sorted(affected))

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a CLI, a console, or CI renders."""
        return {
            "integration": self.integration,
            "ok": self.ok,
            "connectivity": self.connectivity.to_record(),
            "probe": self.probe_description,
            "permissions": [outcome.to_record() for outcome in self.permissions],
            "missing_permissions": list(self.missing_permissions),
            "affected_capabilities": list(self.affected_capabilities),
        }


class VerificationRunner:
    """Runs the declared checks for one integration, or for all of them."""

    __slots__ = ("_verifiers",)

    def __init__(self, verifiers: Iterable[IntegrationVerifier]) -> None:
        held: dict[str, IntegrationVerifier] = {}
        for verifier in verifiers:
            if not verifier.probe_description.strip():
                raise ValueError(
                    f"{verifier.integration}: a verifier must say what call proves "
                    f"connectivity. A vendor with no verification endpoint uses its "
                    f"cheapest read instead, and the substitution has to be written down "
                    f"or nobody can interpret the result."
                )
            held[verifier.integration] = verifier
        self._verifiers = held

    def names(self) -> tuple[str, ...]:
        """Return every integration this runner can check, in name order."""
        return tuple(sorted(self._verifiers))

    async def verify(self, integration: str, *, transport: Any, context: Any) -> VerificationReport:
        """Return what the checks for ``integration`` established.

        Raises:
            LookupError: no verifier is installed under that name.
        """
        verifier = self._verifiers.get(integration)
        if verifier is None:
            raise LookupError(
                f"no integration named {integration!r} declares a verifier. Installed: "
                f"{', '.join(self.names()) or 'none'}"
            )

        connectivity = await verifier.connect(transport, context)
        probes = verifier.probes()
        if not connectivity.reachable:
            outcomes = tuple(
                PermissionOutcome(
                    permission=probe.permission,
                    state=ProbeState.UNCHECKED,
                    detail="the credential was rejected before this could be checked",
                )
                for probe in probes
            )
        else:
            outcomes = tuple([await probe.run(transport, context) for probe in probes])

        return VerificationReport(
            integration=integration,
            connectivity=connectivity,
            permissions=outcomes,
            probe_description=_probe_description(verifier, probes),
        )

    async def verify_all(self, *, transport: Any, context: Any) -> tuple[VerificationReport, ...]:
        """Return a report for every installed integration, in name order."""
        return tuple(
            [await self.verify(name, transport=transport, context=context) for name in self.names()]
        )


def runner_for(descriptors: Iterable[Any]) -> VerificationRunner:
    """Return a runner over the verifiers the given descriptors declare.

    Takes descriptors rather than verifiers so composition hands over the same
    catalogue everything else in the framework reads, instead of a second list
    that has to agree with it.
    """
    return VerificationRunner(
        [
            descriptor.verifier
            for descriptor in descriptors
            if isinstance(descriptor.verifier, IntegrationVerifier)
        ]
    )


def _probe_description(verifier: IntegrationVerifier, probes: tuple[PermissionProbe, ...]) -> str:
    """Return the connectivity description, with any fallback note appended.

    A fallback is FR-011's documented substitution, and it belongs in the report
    rather than only in the source: the person who needs to know that a
    permission was inferred from a log read is the one reading the result.
    """
    notes = [probe.fallback_note.strip() for probe in probes if probe.is_fallback]
    if not notes:
        return verifier.probe_description
    return verifier.probe_description + ". " + "; ".join(notes)


__all__ = [
    "Connectivity",
    "IntegrationVerifier",
    "VerificationReport",
    "VerificationRunner",
    "runner_for",
]
