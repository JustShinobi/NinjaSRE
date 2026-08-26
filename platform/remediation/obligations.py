"""Verification as a durable obligation with a due time, not as a wait.

The naive implementation sleeps inside the run. That does three things, and each
one is worse than the last: it holds the run open past its wall-clock ceiling,
it loses the verification entirely when the process restarts, and it makes the
settle period compete with the investigation's own budget.

So the executor writes a row saying "read these signals about this resource at
14:05, and compare them to these values", the run ends, and a worker picks the
row up when it comes due. The shape is the scheduler's — a durable record, a due
time, a lease — because a second coordination mechanism in one deployment is a
second thing to get wrong.

Three properties are load-bearing.

**The before values are captured immediately prior to execution.** Not read back
from history at verification time: by then the action has run, and the window a
"before" would be averaged over would contain the change. They are on the
obligation row, which is also what makes a verdict arguable — a human who
disagrees with the attribution can see exactly what was compared.

**A resource that has gone quiet is ``inconclusive``.** Reading no sample and
reading a good one are different facts, and the whole of FR-022 is that only one
of them is evidence. ``read_values`` therefore returns a mapping that is missing
the names it could not read rather than defaulting them.

**Nothing here decides what to do about the verdict.** This module reaches one,
records it, and stops. What a ``worsened`` verdict causes is a rollback, what an
``ineffective`` one causes is an escalation, and both belong where the thing
they act on lives.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from config.constants.closed_loop import (
    MAX_VERIFICATION_ATTEMPTS,
    MAX_VERIFICATION_CLAIM_BATCH,
    VERIFICATION_LEASE_SECONDS,
)
from platform.observability.logging import get_logger
from platform.persistence.ports.remediation_ledger import (
    RemediationLedger,
    RemediationOutcome,
    VerificationState,
    VerificationVerdict,
)
from platform.persistence.ports.signal_store import Signal, SignalKind
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork
from platform.remediation.components import ComponentRegistry
from platform.remediation.declaration import VerificationDeclaration
from platform.remediation.models import RemediationAction, utc_now

_LOG = get_logger(__name__)


@runtime_checkable
class SignalReadback(Protocol):
    """Reads the newest sample of each named signal about a resource.

    Narrower than ``SignalStore`` on purpose, and for the same reason
    ``ExecutionIsolation`` is narrower than the sandbox port: verification needs
    exactly one of that port's four operations, and depending on the wider
    interface would let a future caller write a signal from inside the
    verification path.

    ``latest`` rather than a window, deliberately. A window returns nothing both
    for a source that stopped and for a resource nobody watches, and those are
    the same verdict — ``inconclusive`` — only by accident. The newest sample
    however old it is lets the caller see the age and say which happened.
    """

    async def latest(
        self,
        *,
        names: tuple[str, ...] = (),
        resource_ids: tuple[str, ...] = (),
    ) -> tuple[Signal, ...]:
        """Return the newest sample per ``(name, resource)``, however old it is."""


def resource_of(action: RemediationAction) -> str:
    """Return the resource identifier signals about ``action``'s target are keyed by.

    The bare identifier rather than ``identifier@environment``: the estate and
    the signal history know a resource by the id discovery gave it, and the
    environment is a field on the target because two mechanisms read it
    separately. A deployment whose signals are keyed some other way supplies its
    own function; there is one place to change.
    """
    return action.target.identifier


def read_values(
    samples: Sequence[Signal],
    *,
    names: Sequence[str],
    fresh_since: datetime | None = None,
) -> dict[str, float]:
    """Return the numeric value of each named signal, omitting what was not read.

    Omitting rather than defaulting to zero. A missing signal and a signal
    reading zero lead to opposite verdicts — one is "could not tell" and the
    other may be "cleared" — and a default would silently pick the wrong one for
    every absence detector in the deployment.

    ``fresh_since`` discards samples older than the instant given, which is how
    a resource that went absent between the action and the check produces
    ``inconclusive``: its newest sample predates the action, so there is nothing
    to compare.
    """
    wanted = set(names)
    values: dict[str, float] = {}
    for sample in samples:
        if sample.name not in wanted or sample.kind is not SignalKind.NUMBER:
            continue
        if fresh_since is not None and sample.observed_at < fresh_since:
            continue
        values[sample.name] = sample.value
    return values


@dataclass(frozen=True, slots=True)
class Verification:
    """One obligation, read back and judged.

    Carries the row it updated as well as the verdict, because every caller
    downstream needs both: the rollback needs the plan identifier, the
    escalation needs the incident, and the recurrence count needs the pattern.
    """

    outcome: RemediationOutcome
    verdict: VerificationVerdict
    before: Mapping[str, float] = field(default_factory=dict)
    after: Mapping[str, float] = field(default_factory=dict)
    #: Whether this is the verdict or a report that the obligation was deferred.
    #: A deferral carries ``INCONCLUSIVE`` because that is what is known so far,
    #: and a caller acting on it would escalate an action that is still
    #: settling — so the flag is checked rather than the verdict alone.
    settled: bool = True

    @property
    def action_id(self) -> str:
        """Return the action this verifies."""
        return self.outcome.action_id

    def describe(self) -> str:
        """Return the sentence an operator reads under the action."""
        moved = ", ".join(
            f"{name} {self.before.get(name, float('nan')):g} → {value:g}"
            for name, value in sorted(self.after.items())
        )
        if self.verdict is VerificationVerdict.UNVERIFIABLE:
            return (
                f"{self.outcome.capability} on {self.outcome.resource_id} declares no "
                f"signal its effect would appear in, so whether it helped is unknown."
            )
        if not moved:
            return (
                f"{self.outcome.capability} on {self.outcome.resource_id}: nothing could "
                f"be read back after the settle period, so the result is inconclusive."
            )
        return f"{self.outcome.capability} on {self.outcome.resource_id}: {moved}."


@dataclass(slots=True)
class VerificationObligations:
    """Writes the obligation before the run ends, and settles it when it is due.

    Holds the ledger and a signal readback and nothing else that decides
    anything. ``owe`` is called by the executor while it still has the action;
    ``settle`` is called by a worker that has claimed the row and never has the
    action at all — which is exactly why the row carries everything a verdict
    needs rather than a reference to something in memory.
    """

    ledger: RemediationLedger
    signals: SignalReadback
    registry: ComponentRegistry
    clock: Callable[[], datetime] = field(default=utc_now)
    resource_for: Callable[[RemediationAction], str] = field(default=resource_of)

    def declaration_for(self, capability: str) -> VerificationDeclaration:
        """Return how ``capability``'s effect is verified, whatever it declared."""
        return self.registry.verification_of(capability)

    async def capture(self, action: RemediationAction) -> dict[str, float]:
        """Return the declared signals' values as they stand right now.

        Called immediately before the change, which is the whole of T-006. A
        "before" read afterwards would be read from a window containing the
        action, and every verdict computed from it would understate the effect.
        """
        declaration = self.declaration_for(action.capability)
        if not declaration.verifiable:
            return {}
        samples = await self.signals.latest(
            names=declaration.names,
            resource_ids=(self.resource_for(action),),
        )
        return read_values(samples, names=declaration.names)

    async def owe(
        self,
        action: RemediationAction,
        *,
        before: Mapping[str, float],
        executed_at: datetime,
        autonomous: bool = False,
        plan_id: str = "",
        incident_id: str = "",
        condition_key: str = "",
        undo: Mapping[str, Any] | None = None,
    ) -> RemediationOutcome:
        """Record what is owed about ``action``, and return the row.

        Returns without waiting. The settle period may be longer than the run's
        own wall-clock ceiling — NFR-002 — and the only shape in which that is
        true is one where the run does not hold the verification open.
        """
        declaration = self.declaration_for(action.capability)
        due_at = executed_at + timedelta(seconds=declaration.settle_seconds)
        unverifiable = not declaration.verifiable

        outcome = RemediationOutcome(
            action_id=action.action_id,
            capability=action.capability,
            resource_id=self.resource_for(action),
            condition_key=condition_key,
            team_node_id=action.team_node_id or "",
            incident_id=incident_id,
            run_id=action.run_id,
            plan_id=plan_id,
            executed_at=executed_at,
            due_at=due_at,
            settle_seconds=declaration.settle_seconds,
            # An unverifiable capability is settled the moment it is recorded.
            # Leaving it awaiting a verification that can never happen would
            # show "awaiting verification" for ever on a surface where that
            # phrase is supposed to mean "ask again shortly".
            state=VerificationState.VERIFIED if unverifiable else VerificationState.AWAITING,
            verdict=VerificationVerdict.UNVERIFIABLE if unverifiable else None,
            signal_names=declaration.names,
            before=dict(before),
            verified_at=executed_at if unverifiable else None,
            detail=declaration.reason if unverifiable else "",
            autonomous=autonomous,
            undo=dict(undo) if undo else {},
        )
        stored = await self.ledger.record(outcome)
        _LOG.info(
            "remediation.verification_owed",
            action_id=action.action_id,
            capability=action.capability,
            resource_id=stored.resource_id,
            due_at=due_at.isoformat(),
            settle_seconds=declaration.settle_seconds,
            verifiable=not unverifiable,
        )
        return stored

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime | None = None,
        lease_seconds: float = VERIFICATION_LEASE_SECONDS,
        limit: int = MAX_VERIFICATION_CLAIM_BATCH,
    ) -> tuple[RemediationOutcome, ...]:
        """Return the obligations due now that no other worker holds."""
        at = now if now is not None else self.clock()
        return await self.ledger.claim_due(
            now=at, worker_id=worker_id, lease_seconds=lease_seconds, limit=limit
        )

    async def settle(
        self,
        outcome: RemediationOutcome,
        *,
        now: datetime | None = None,
    ) -> Verification:
        """Read the declared signals back and record the verdict they reach.

        The verdict is recorded here rather than returned for somebody else to
        record. A worker that reached a verdict and died before writing it would
        leave the obligation to be claimed again and re-judged against signals
        that have since moved — which is how one action acquires two histories.
        """
        at = now if now is not None else self.clock()
        declaration = self.declaration_for(outcome.capability)

        if not declaration.verifiable:
            return await self._record(
                outcome,
                verdict=VerificationVerdict.UNVERIFIABLE,
                after={},
                at=at,
                detail=declaration.reason,
            )

        samples = await self.signals.latest(
            names=declaration.names, resource_ids=(outcome.resource_id,)
        )
        # Only samples taken after the action counts as evidence about it. A
        # resource that went absent still has its last reading, and comparing
        # against that would credit the action with the state it was trying to
        # change.
        after = read_values(samples, names=declaration.names, fresh_since=outcome.executed_at)
        verdict = declaration.verdict_for(before=outcome.before, after=after)

        if not after and outcome.attempts < MAX_VERIFICATION_ATTEMPTS:
            # Nothing readable yet and attempts left: leave it owed, due again
            # after another settle period, rather than concluding from silence.
            return await self._retry(outcome, at=at, settle=declaration.settle_seconds)

        return await self._record(outcome, verdict=verdict, after=after, at=at)

    async def _record(
        self,
        outcome: RemediationOutcome,
        *,
        verdict: VerificationVerdict,
        after: Mapping[str, float],
        at: datetime,
        detail: str = "",
    ) -> Verification:
        """Write the verdict onto the obligation and return the verification."""
        settled = replace(
            outcome,
            state=VerificationState.VERIFIED,
            verdict=verdict,
            after=dict(after),
            verified_at=at,
            detail=detail or outcome.detail,
            lease_holder="",
            lease_expires_at=None,
        )
        stored = await self.ledger.record(settled)
        _LOG.info(
            "remediation.verified",
            action_id=stored.action_id,
            capability=stored.capability,
            resource_id=stored.resource_id,
            verdict=verdict.value,
            attempts=stored.attempts,
        )
        return Verification(
            outcome=stored, verdict=verdict, before=dict(stored.before), after=dict(after)
        )

    async def _retry(
        self,
        outcome: RemediationOutcome,
        *,
        at: datetime,
        settle: int,
    ) -> Verification:
        """Push the obligation out by one settle period and leave it owed."""
        again = replace(
            outcome,
            state=VerificationState.AWAITING,
            due_at=at + timedelta(seconds=settle),
            lease_holder="",
            lease_expires_at=None,
        )
        stored = await self.ledger.record(again)
        _LOG.warning(
            "remediation.verification_deferred",
            action_id=stored.action_id,
            resource_id=stored.resource_id,
            attempts=stored.attempts,
            due_at=stored.due_at.isoformat(),
        )
        return Verification(
            outcome=stored,
            verdict=VerificationVerdict.INCONCLUSIVE,
            before=dict(stored.before),
            settled=False,
        )


@runtime_checkable
class VerificationRecorder(Protocol):
    """What the executor needs from the closed loop, and nothing more.

    Two operations either side of the change: read the declared signals as they
    stand, and write down what is owed. Narrower than
    ``VerificationObligations`` on purpose — the executor must not be able to
    reach a verdict, because a verdict reached inside the run is a verdict
    reached before the settle period.
    """

    async def capture(self, action: RemediationAction) -> Mapping[str, float]:
        """Return the declared signals' values as they stand right now."""

    async def owe(
        self,
        action: RemediationAction,
        *,
        before: Mapping[str, float],
        executed_at: datetime,
        autonomous: bool = False,
        plan_id: str = "",
        incident_id: str = "",
        condition_key: str = "",
        undo: Mapping[str, Any] | None = None,
    ) -> RemediationOutcome:
        """Record what is owed about ``action``, and return the row."""


@dataclass(slots=True)
class LedgerVerification:
    """A recorder that opens its own unit of work per call.

    What a long-lived executor holds. ``VerificationObligations`` takes a ledger
    bound to one transaction, which suits a worker settling a claimed obligation
    and does not suit an executor that lives for the life of the process — so
    this is the adapter between the two, and it is the same shape
    ``AuditSpendLedger`` uses for the same reason.

    ``signals_for`` is a function of the unit of work rather than a readback
    held on the field, and the difference is what makes the before-values real.
    The readback is asked from inside the transaction this class opens, so an
    implementation holding its own handle would take a second connection while
    the first is open — against the in-memory backend that deadlocks. Reading
    through the unit of work already in hand has neither problem, and a
    deployment that captured nothing before every change is one whose every
    verdict is ``inconclusive`` for ever.
    """

    gateway: PersistenceGateway
    scope: TenantScope
    signals_for: Callable[[UnitOfWork], SignalReadback]
    registry: ComponentRegistry
    clock: Callable[[], datetime] = field(default=utc_now)
    resource_for: Callable[[RemediationAction], str] = field(default=resource_of)

    async def capture(self, action: RemediationAction) -> Mapping[str, float]:
        """Return the declared signals' values as they stand right now."""
        async with self.gateway.begin(self.scope) as uow:
            return await self._over(uow).capture(action)

    async def owe(
        self,
        action: RemediationAction,
        *,
        before: Mapping[str, float],
        executed_at: datetime,
        autonomous: bool = False,
        plan_id: str = "",
        incident_id: str = "",
        condition_key: str = "",
        undo: Mapping[str, Any] | None = None,
    ) -> RemediationOutcome:
        """Record what is owed about ``action``, and return the row."""
        async with self.gateway.begin(self.scope) as uow:
            return await self._over(uow).owe(
                action,
                before=before,
                executed_at=executed_at,
                autonomous=autonomous,
                plan_id=plan_id,
                incident_id=incident_id,
                condition_key=condition_key,
                undo=undo,
            )

    def _over(self, uow: UnitOfWork) -> VerificationObligations:
        """Return the obligations service bound to one transaction."""
        return VerificationObligations(
            ledger=uow.remediation,
            signals=self.signals_for(uow),
            registry=self.registry,
            clock=self.clock,
            resource_for=self.resource_for,
        )


__all__ = [
    "LedgerVerification",
    "SignalReadback",
    "Verification",
    "VerificationObligations",
    "VerificationRecorder",
    "read_values",
    "resource_of",
]
