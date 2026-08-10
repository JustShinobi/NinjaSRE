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

**A signal source is asked two further questions, and only a signal source.**
``SignalSourceVerifier`` is a second protocol rather than two more methods on
the first, because the first is implemented by around ninety verifiers and a
widened protocol would either break all of them or acquire defaults that report
an unmeasured clock as an agreeing one. A verifier that declares neither method
is not a signal source, its report carries neither result, and nothing about it
changes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from integrations._verification.diagnostics import (
    ClockSkewOutcome,
    ClockSkewProbe,
    DataWindow,
    DataWindowOutcome,
    DataWindowProbe,
    SkewState,
)
from integrations._verification.permissions import (
    PermissionOutcome,
    PermissionProbe,
    ProbeState,
)


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


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


@runtime_checkable
class SignalSourceVerifier(Protocol):
    """A verifier for a vendor an investigation *reads signals out of*.

    Declared by the metric, log, trace, alert and dashboard vendors and by
    nothing else. Both methods may return ``None`` — a vendor that answers only
    one of the two questions says so by returning ``None`` from the other rather
    than by supplying a probe that measures nothing.
    """

    def data_window_probe(self) -> DataWindowProbe | None:
        """Return the read that proves this source holds recent data, if it can."""

    def clock_probe(self) -> ClockSkewProbe | None:
        """Return the reading that says what time this source thinks it is."""


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """What one integration's verification established, in full."""

    integration: str
    connectivity: Connectivity
    permissions: tuple[PermissionOutcome, ...] = ()
    probe_description: str = ""
    #: Present only for a signal source. ``None`` for the rest of the catalogue,
    #: and deliberately not an empty outcome: an outcome with no reading in it
    #: renders as a measurement that came back clean.
    data_window: DataWindowOutcome | None = None
    clock: ClockSkewOutcome | None = None

    @property
    def ok(self) -> bool:
        """Return whether the integration is usable as configured.

        Reachable, nothing denied, and — for a signal source — able to answer a
        question about the recent past. An inconclusive probe does not fail the
        report, because nothing was established and failing on "we could not
        tell" would make a rate-limited verification run look like a broken
        credential. A skewed clock does not fail it either: the source answers,
        and what cannot be trusted is one field of the answer. That is
        ``degraded``, below.
        """
        if not self.connectivity.reachable:
            return False
        if any(outcome.denied for outcome in self.permissions):
            return False
        return self.data_window is None or self.data_window.usable

    @property
    def degradations(self) -> tuple[str, ...]:
        """Return the reasons this source's answers cannot be taken at face value.

        Prose rather than codes, and each line names the measurement it came
        from. These are the sentences that go in front of an operator, so a
        reason nobody can act on is a reason that should not be here.
        """
        reasons: list[str] = []
        window = self.data_window
        if window is not None and window.is_finding:
            reasons.append(
                f"it answered and holds nothing for the last {window.window_minutes} minutes. "
                f"{window.advice}"
            )
        clock = self.clock
        if clock is not None and clock.degraded and clock.offset_seconds is not None:
            reasons.append(
                f"its clock is {abs(clock.offset_seconds):.1f}s from the platform's, outside "
                f"the {clock.tolerance_seconds:.1f}s that correlation tolerates — every "
                f"timestamp it contributes to a timeline is offset by that much"
            )
        return tuple(reasons)

    @property
    def degraded(self) -> bool:
        """Return whether something measured here makes this source's answers unsafe."""
        return bool(self.degradations)

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
        """Return the JSON-serialisable form a CLI, a console, or CI renders.

        The two signal-source keys are absent rather than null for a vendor that
        is not one. A reader iterating the document has to be able to tell "this
        was not measured" from "this measured nothing", and a null in a schema
        that also uses null for an unread clock cannot.
        """
        record: dict[str, object] = {
            "integration": self.integration,
            "ok": self.ok,
            "degraded": self.degraded,
            "degradations": list(self.degradations),
            "connectivity": self.connectivity.to_record(),
            "probe": self.probe_description,
            "permissions": [outcome.to_record() for outcome in self.permissions],
            "missing_permissions": list(self.missing_permissions),
            "affected_capabilities": list(self.affected_capabilities),
        }
        if self.data_window is not None:
            record["data_window"] = self.data_window.to_record()
        if self.clock is not None:
            record["clock"] = self.clock.to_record()
        return record


class VerificationRunner:
    """Runs the declared checks for one integration, or for all of them."""

    __slots__ = ("_clock", "_verifiers")

    def __init__(
        self,
        verifiers: Iterable[IntegrationVerifier],
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        # Injected rather than read at the call site so a suite can pin it. The
        # skew measurement is a subtraction against this instant, and a test
        # that read the wall clock would assert against how long it took to get
        # there.
        self._clock = clock
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

        window, clock = await self._signals(
            verifier, transport=transport, context=context, reachable=connectivity.reachable
        )
        return VerificationReport(
            integration=integration,
            connectivity=connectivity,
            permissions=outcomes,
            probe_description=_probe_description(verifier, probes),
            data_window=window,
            clock=clock,
        )

    async def _signals(
        self,
        verifier: IntegrationVerifier,
        *,
        transport: Any,
        context: Any,
        reachable: bool,
    ) -> tuple[DataWindowOutcome | None, ClockSkewOutcome | None]:
        """Return what this vendor's signal-source probes found, if it has any.

        Connectivity gates these the same way it gates the permission probes,
        and for the same reason: a credential the vendor rejected produces an
        empty answer from every read, and reporting that as an empty store would
        send an operator to their scrape configuration over a bad token.
        """
        if not isinstance(verifier, SignalSourceVerifier):
            return None, None

        now = self._clock()
        span = DataWindow.ending_at(now)
        window_probe = verifier.data_window_probe()
        clock_probe = verifier.clock_probe()

        window: DataWindowOutcome | None = None
        if window_probe is not None:
            window = (
                await window_probe.run(transport, context, window=span)
                if reachable
                else window_probe.unchecked(span)
            )

        clock: ClockSkewOutcome | None = None
        if clock_probe is not None:
            clock = (
                await clock_probe.run(transport, context, now=now)
                if reachable
                else clock_probe.unchecked()
            )
        return window, clock

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
    "SignalSourceVerifier",
    "SkewState",
    "VerificationReport",
    "VerificationRunner",
    "runner_for",
]
